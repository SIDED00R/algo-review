import os
import subprocess
import sys
import tempfile
import time

from fastapi import APIRouter, HTTPException

from config import settings
from demo_mode import IS_DEMO, demo_block
from routes.models import ExecuteRequest

router = APIRouter()

# 코드 실행 subprocess에는 최소한의 환경변수만 전달해 민감한 서버 설정이 새지 않도록 한다.
_SAFE_ENV_KEYS = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE", "LANG", "LC_ALL"}
_COMPILE_TIMEOUT = settings.compile_timeout


def safe_env() -> dict:
    """subprocess 에 넘길 환경변수. **호출 시점에** os.environ 을 필터한다.

    import 시점 상수로 두면 테스트가 센티넬 키를 심어도 이미 만들어진 dict 에 반영되지
    않아 이 필터를 실효 검증할 수 없다.
    """
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
# preexec_fn은 멀티스레드 서버(FastAPI threadpool)에서 fork 후 exec 전 deadlock 위험이 있어 사용하지 않는다.
# 메모리·프로세스 제한은 Cloud Run 서비스 설정(컨테이너 메모리 상한)과 timeout에 위임한다.


def _run_python(code: str, stdin: str, timeout: int) -> dict:
    # UTF-8·무버퍼는 커맨드라인 플래그로 준다 — -I 가 모든 PYTHON* 환경변수를 무시한다.
    env = safe_env()
    try:
        # 작업 디렉터리를 격리한다 — cwd 를 지정하지 않으면 sys.path[0] 가 리포 루트가 되어
        # 제출 코드가 `import config` 로 .env 를 읽는다. -I 는 환경변수·사용자 site import 를 끊는다.
        with tempfile.TemporaryDirectory() as tmpdir:
            result = subprocess.run(
                [sys.executable, "-I", "-X", "utf8=1", "-u", "-c", code],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=env,
                cwd=tmpdir,
            )
            return {"stdout": result.stdout, "stderr": result.stderr,
                    "exit_code": result.returncode}
    except subprocess.TimeoutExpired:
        return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}
    except FileNotFoundError:
        return {"stdout": "", "stderr": "[Python 실행 환경을 찾을 수 없습니다]", "exit_code": -1}


def _run_cpp(code: str, stdin: str, timeout: int) -> dict:
    with tempfile.TemporaryDirectory() as tmpdir:
        src = os.path.join(tmpdir, "sol.cpp")
        exe = os.path.join(tmpdir, "sol.exe" if os.name == "nt" else "sol")
        with open(src, "w", encoding="utf-8") as file:
            file.write(code)
        try:
            compile_result = subprocess.run(
                ["g++", "-O2", "-std=c++17", "-o", exe, src],
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=_COMPILE_TIMEOUT,
                env=safe_env(),
                cwd=tmpdir,   # 실행 단계와 같은 이유 — 서버 CWD 를 상속하지 않는다
            )
        except FileNotFoundError:
            return {"stdout": "", "stderr": "[g++ 컴파일러를 찾을 수 없습니다]", "exit_code": -1}
        except subprocess.TimeoutExpired:
            # 컴파일도 실행과 같이 시간 초과를 잡는다. 잡지 않으면 과도한 템플릿 재귀 등으로
            # 컴파일이 길어질 때 예외가 라우터를 탈출해 원인 불명 500 이 된다.
            return {"stdout": "", "stderr": f"[컴파일 시간 초과 - {_COMPILE_TIMEOUT}초]",
                    "exit_code": -1}
        if compile_result.returncode != 0:
            return {"stdout": "", "stderr": compile_result.stderr, "exit_code": compile_result.returncode}
        try:
            run_result = subprocess.run(
                [exe],
                input=stdin,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout,
                env=safe_env(),
                cwd=tmpdir,   # 서버 CWD 를 상속하지 않는다 — 파이썬 경로와 같은 이유
            )
            return {"stdout": run_result.stdout, "stderr": run_result.stderr, "exit_code": run_result.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}


@router.post("/api/execute")
def execute_code(req: ExecuteRequest):
    # 데모는 공개 배포라 임의 코드 실행을 열어둘 수 없다(import 계열은 이미 차단돼 있다).
    if IS_DEMO:
        demo_block("코드 실행은 데모 버전에서 지원되지 않습니다.")
    # 자식 프로세스가 앱과 같은 uid·같은 네트워크 네임스페이스에서 도는 한 메타데이터 서버
    # (egress)와 /proc/1/environ 경로가 남는다. 컨테이너 안에서는 막을 수 없다.
    if not settings.execute_enabled:
        raise HTTPException(
            status_code=403,
            detail="코드 실행이 비활성화되어 있습니다. 로컬에서 EXECUTE_ENABLED=true 로 실행해주세요.")
    start = time.time()
    lang = req.language.lower()
    if "python" in lang or "pypy" in lang:
        result = _run_python(req.code, req.stdin, req.timeout_sec)
    elif "c++" in lang or "cpp" in lang or "gnu" in lang:
        result = _run_cpp(req.code, req.stdin, req.timeout_sec)
    else:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: {req.language}")
    result["time_ms"] = int((time.time() - start) * 1000)
    return result
