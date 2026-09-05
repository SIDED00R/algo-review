"""제출 코드를 자식 프로세스로 실행한다.

실행 전용 서비스(`executor/main.py`)가 쓴다. 앱 모듈을 import 하지 않는다 — 실행 서비스
이미지에는 앱 코드가 들어가지 않는다.
"""
import os
import signal
import subprocess
import sys
import tempfile
import threading
import time

MAX_CODE_LENGTH = 50_000
# stdin 은 파이프 버퍼(리눅스 기본 64KB)보다 클 수 있어 별도 스레드로 쓴다. 상한은 그와
# 무관하게 메모리를 묶기 위한 것이다.
MAX_STDIN_BYTES = 64 * 1024
# 스트림당 상한. 넘는 바이트는 읽어서 버린다 — 파이프를 계속 비워야 자식이 write 에서
# 막히지 않으면서도 버퍼가 이 크기를 넘지 않는다.
MAX_OUTPUT_BYTES = 64 * 1024
MAX_TIMEOUT_SEC = 10
COMPILE_TIMEOUT_SEC = int(os.getenv("COMPILE_TIMEOUT", "30"))

# 자식에게 넘길 환경변수 화이트리스트. 이 필터가 있어야 어떤 호스트에서 돌든 부모 프로세스의
# 환경이 제출 코드로 새지 않는다.
_SAFE_ENV_KEYS = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE", "LANG", "LC_ALL"}

_TRUNCATED_NOTICE = f"\n[출력이 {MAX_OUTPUT_BYTES // 1024}KB 에서 잘렸습니다]"


class UnsupportedLanguage(ValueError):
    """호출부가 400 으로 바꿀 수 있도록 언어 오류만 따로 구분한다."""


def safe_env() -> dict:
    """subprocess 에 넘길 환경변수. **호출 시점에** os.environ 을 필터한다.

    import 시점 상수로 두면 테스트가 센티넬 키를 심어도 이미 만들어진 dict 에 반영되지
    않아 이 필터를 실효 검증할 수 없다.
    """
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}


def _spawn(cmd: list[str], cwd: str) -> subprocess.Popen:
    # 새 세션으로 띄워 프로세스 그룹째 죽일 수 있게 한다 — 제출 코드가 자식을 남기면
    # 직접 자식만 kill 해서는 손자가 인스턴스 수명 동안 CPU 를 계속 쓴다.
    # preexec_fn 은 쓰지 않는다(멀티스레드에서 fork 후 exec 전 deadlock 위험).
    extra = {"start_new_session": True} if os.name == "posix" else {}
    return subprocess.Popen(
        cmd,
        stdin=subprocess.PIPE,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd=cwd,
        env=safe_env(),
        **extra,
    )


def _kill_tree(proc: subprocess.Popen, pgid: int | None) -> None:
    """자식이 이미 끝났어도 호출한다 — 손자가 남아 파이프를 붙잡고 있을 수 있다.

    pgid 를 인자로 받는 이유: `wait()` 로 자식이 회수된 뒤에는 `os.getpgid(proc.pid)` 가
    ProcessLookupError 를 던져 손자를 죽일 수 없다. 그룹에 멤버가 남아 있는 한 커널은 그
    번호를 다른 프로세스에 재사용하지 않으므로, 처음에 확보한 값을 그대로 쓴다.
    """
    if pgid is not None:
        try:
            os.killpg(pgid, signal.SIGKILL)
        except (ProcessLookupError, PermissionError, OSError):
            pass
        return
    # 윈도우(로컬 개발)에는 프로세스 그룹 종료가 없다 — 직접 자식만 죽는다.
    try:
        proc.kill()
    except OSError:
        pass


def _pump(stream, sink: bytearray, truncated: list) -> None:
    try:
        while True:
            chunk = stream.read1(8192)
            if not chunk:
                break
            room = MAX_OUTPUT_BYTES - len(sink)
            if room > 0:
                if len(chunk) > room:
                    truncated[0] = True
                sink += chunk[:room]
            else:
                truncated[0] = True
    except (ValueError, OSError):
        # kill 이후 닫힌 파이프. 읽던 것까지가 결과다.
        pass
    finally:
        _close(stream)


def _feed(stream, data: bytes) -> None:
    try:
        stream.write(data)
        stream.flush()
    except (BrokenPipeError, ValueError, OSError):
        # 자식이 입력을 읽지 않고 끝났다 — 정상적인 제출 코드에서도 흔하다.
        pass
    finally:
        _close(stream)


def _close(stream) -> None:
    try:
        stream.close()
    except (ValueError, OSError):
        pass


def _decode(buf: bytearray, truncated: bool) -> str:
    # 개행을 LF 로 통일한다 — 윈도우 로컬에서 자식이 내는 CRLF 가 그대로 나가면 프론트의
    # 예제 출력 비교가 어긋난다(파이프를 바이트로 읽으므로 자동 변환이 없다).
    text = buf.decode("utf-8", errors="replace").replace("\r\n", "\n").replace("\r", "\n")
    return text + _TRUNCATED_NOTICE if truncated else text


def _execute(cmd: list[str], stdin: bytes, timeout: int, cwd: str) -> dict:
    """출력 상한·프로세스 그룹 종료를 건 실행. 시간 초과면 exit_code -1."""
    proc = _spawn(cmd, cwd)
    # start_new_session 이라 자식이 그룹 리더이고 그룹 id 는 자식의 pid 와 같다.
    # 회수 전에 확보해 둔다 — 회수 뒤에는 pid 로 그룹을 되찾을 수 없다.
    pgid = proc.pid if os.name == "posix" else None
    out, err = bytearray(), bytearray()
    out_truncated, err_truncated = [False], [False]
    workers = [
        threading.Thread(target=_pump, args=(proc.stdout, out, out_truncated), daemon=True),
        threading.Thread(target=_pump, args=(proc.stderr, err, err_truncated), daemon=True),
        threading.Thread(target=_feed, args=(proc.stdin, stdin), daemon=True),
    ]
    for worker in workers:
        worker.start()
    timed_out = False
    try:
        proc.wait(timeout=timeout)
    except subprocess.TimeoutExpired:
        timed_out = True
    # 그룹을 먼저 죽여야 파이프가 닫히고 pump 스레드가 끝난다.
    _kill_tree(proc, pgid)
    exit_code = proc.wait()
    for worker in workers:
        worker.join(timeout=1)
    if timed_out:
        return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}
    return {"stdout": _decode(out, out_truncated[0]), "stderr": _decode(err, err_truncated[0]),
            "exit_code": exit_code}


def _run_python(code: str, stdin: bytes, timeout: int) -> dict:
    # -I 는 PYTHON* 환경변수를 전부 무시하고(-E) 사용자 site·스크립트 디렉터리를 sys.path 에서 뺀다.
    # 그래서 UTF-8·무버퍼는 환경변수가 아니라 커맨드라인 플래그로 준다.
    # cwd 는 임시 디렉터리다 — 제출 코드가 만드는 파일과 상대 경로 접근이 여기 갇힌다.
    try:
        with tempfile.TemporaryDirectory() as tmpdir:
            return _execute([sys.executable, "-I", "-X", "utf8=1", "-u", "-c", code],
                            stdin, timeout, tmpdir)
    except FileNotFoundError:
        return {"stdout": "", "stderr": "[Python 실행 환경을 찾을 수 없습니다]", "exit_code": -1}


def _run_cpp(code: str, stdin: bytes, timeout: int, compile_timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "sol.cpp")
        exe = os.path.join(tmpdir, "sol.exe" if os.name == "nt" else "sol")
        with open(src, "w", encoding="utf-8") as file:
            file.write(code)
        try:
            proc = _spawn(["g++", "-O2", "-std=c++17", "-o", exe, src], tmpdir)
        except FileNotFoundError:
            return {"stdout": "", "stderr": "[g++ 컴파일러를 찾을 수 없습니다]", "exit_code": -1}
        # g++ 가 cc1plus/as/ld 를 자식으로 띄우므로 타임아웃 시 그룹째 죽여야 한다.
        pgid = proc.pid if os.name == "posix" else None
        _close(proc.stdin)   # 컴파일은 입력을 읽지 않는다
        out, err = bytearray(), bytearray()
        err_truncated = [False]
        workers = [
            threading.Thread(target=_pump, args=(proc.stdout, out, [False]), daemon=True),
            threading.Thread(target=_pump, args=(proc.stderr, err, err_truncated), daemon=True),
        ]
        for worker in workers:
            worker.start()
        try:
            proc.wait(timeout=compile_timeout)
        except subprocess.TimeoutExpired:
            # 컴파일도 실행과 같이 시간 초과를 잡는다. 잡지 않으면 과도한 템플릿 재귀 등으로
            # 컴파일이 길어질 때 예외가 라우터를 탈출해 원인 불명 500 이 된다.
            _kill_tree(proc, pgid)
            proc.wait()
            for worker in workers:
                worker.join(timeout=1)
            return {"stdout": "", "stderr": f"[컴파일 시간 초과 - {compile_timeout}초]", "exit_code": -1}
        returncode = proc.wait()
        for worker in workers:
            worker.join(timeout=1)
        if returncode != 0:
            return {"stdout": "", "stderr": _decode(err, err_truncated[0]), "exit_code": returncode}
        return _execute([exe], stdin, timeout, tmpdir)


def run_code(language: str, code: str, stdin: str = "", timeout_sec: int = 5) -> dict:
    """언어별 실행. 상한(타임아웃·stdin 크기)은 여기서 강제한다 — 호출부를 믿지 않는다."""
    timeout = max(1, min(int(timeout_sec), MAX_TIMEOUT_SEC))
    payload = stdin.encode("utf-8")[:MAX_STDIN_BYTES]
    lang = language.lower()
    start = time.time()
    if "python" in lang or "pypy" in lang:
        result = _run_python(code, payload, timeout)
    elif "c++" in lang or "cpp" in lang or "gnu" in lang:
        result = _run_cpp(code, payload, timeout, COMPILE_TIMEOUT_SEC)
    else:
        raise UnsupportedLanguage(f"지원하지 않는 언어: {language}")
    result["time_ms"] = int((time.time() - start) * 1000)
    return result
