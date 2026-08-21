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

    import 시점 상수로 두면 이 필터를 실효 검증할 수 없다 — 테스트가 센티넬 키를 심어도
    이미 만들어진 dict 에는 반영되지 않아, 필터를 통째로 지워도 스위트가 초록이었다
    (변이로 확인). 호출 시점 계산이면 회귀 테스트가 실제로 필터를 태운다.
    """
    return {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
# preexec_fn은 멀티스레드 서버(FastAPI threadpool)에서 fork 후 exec 전 deadlock 위험이 있어 사용하지 않는다.
# 메모리·프로세스 제한은 Cloud Run 서비스 설정(컨테이너 메모리 상한)과 timeout에 위임한다.


def _run_python(code: str, stdin: str, timeout: int) -> dict:
    # UTF-8·무버퍼는 **커맨드라인 플래그**로 준다. -I 는 -E 를 포함해 모든 PYTHON* 환경변수를
    # 무시하므로 PYTHONIOENCODING/PYTHONUTF8 를 넣어도 적용되지 않는다(실측: 비-ASCII 를
    # 출력하는 제출 코드가 Windows 에서 UnicodeEncodeError 로 죽었다).
    env = safe_env()
    try:
        # 작업 디렉터리를 격리한다. cwd 를 지정하지 않으면 서버의 CWD 를 상속해
        # sys.path[0] 가 리포 루트가 되고, 제출 코드가 `import config` 로 .env 를 읽을 수
        # 있다(config 의 env_file 은 CWD 상대 경로다). -I 는 환경변수·사용자 site 기반
        # import 까지 끊는다. 환경변수 필터만으로는 이 경로가 막히지 않았다.
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
            # 실행 단계는 이 예외를 잡는데 컴파일 단계는 잡지 않아, 과도한 템플릿 재귀 등으로
            # 컴파일이 오래 걸리면 예외가 라우터를 탈출해 30초 뒤 원인 불명 500 이 됐다.
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
    # 운영도 공개 배포다(allUsers) — 예전에는 데모만 막고 운영은 열려 있었다.
    # 자식 프로세스는 앱과 같은 uid·같은 네트워크 네임스페이스에서 돌기 때문에,
    # 환경변수 필터·cwd 격리·-I 를 다 걸어도 두 경로가 남는다:
    #   ① 네트워크 egress → GCE 메타데이터 서버 → 런타임 SA 액세스 토큰
    #   ② /proc/1/environ → 앱 프로세스의 환경변수 전체(같은 uid 면 읽힌다)
    # 둘 다 컨테이너 안에서는 막을 수 없다(네트워크 차단은 NET_ADMIN 이 필요하다).
    # 그래서 기본 비활성이고, 켜려면 실행 전용 신뢰 경계를 먼저 만들어야 한다
    # (권한 0 서비스 계정 + 시크릿 미주입 + egress 제한).
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
        raise HTTPException(400, f"지원하지 않는 언어: {req.language}")
    result["time_ms"] = int((time.time() - start) * 1000)
    return result
