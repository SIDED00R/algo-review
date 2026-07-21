import os
import subprocess
import sys
import tempfile
import time

from fastapi import APIRouter, HTTPException

from config import settings
from routes.models import ExecuteRequest

router = APIRouter()

# 코드 실행 subprocess에는 최소한의 환경변수만 전달해 민감한 서버 설정이 새지 않도록 한다.
_SAFE_ENV_KEYS = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE", "LANG", "LC_ALL"}
_BASE_ENV = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
_COMPILE_TIMEOUT = settings.compile_timeout
# preexec_fn은 멀티스레드 서버(FastAPI threadpool)에서 fork 후 exec 전 deadlock 위험이 있어 사용하지 않는다.
# 메모리·프로세스 제한은 Cloud Run 서비스 설정(컨테이너 메모리 상한)과 timeout에 위임한다.


def _run_python(code: str, stdin: str, timeout: int) -> dict:
    env = {**_BASE_ENV, "PYTHONUNBUFFERED": "1", "PYTHONIOENCODING": "utf-8", "PYTHONUTF8": "1"}
    try:
        result = subprocess.run(
            [sys.executable, "-c", code],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        return {"stdout": result.stdout, "stderr": result.stderr, "exit_code": result.returncode}
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
                timeout=_COMPILE_TIMEOUT,
                env=_BASE_ENV,
            )
        except FileNotFoundError:
            return {"stdout": "", "stderr": "[g++ 컴파일러를 찾을 수 없습니다]", "exit_code": -1}
        if compile_result.returncode != 0:
            return {"stdout": "", "stderr": compile_result.stderr, "exit_code": compile_result.returncode}
        try:
            run_result = subprocess.run(
                [exe],
                input=stdin,
                capture_output=True,
                text=True,
                timeout=timeout,
                env=_BASE_ENV,
            )
            return {"stdout": run_result.stdout, "stderr": run_result.stderr, "exit_code": run_result.returncode}
        except subprocess.TimeoutExpired:
            return {"stdout": "", "stderr": f"[시간 초과 - {timeout}초]", "exit_code": -1}


@router.post("/api/execute")
def execute_code(req: ExecuteRequest):
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
