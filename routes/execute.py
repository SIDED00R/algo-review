import os
import subprocess
import sys
import tempfile
import time

from fastapi import APIRouter, HTTPException

from routes.models import ExecuteRequest

router = APIRouter()

# 코드 실행 subprocess에는 최소한의 환경변수만 전달해 민감한 서버 설정이 새지 않도록 한다.
_SAFE_ENV_KEYS = {"PATH", "HOME", "TEMP", "TMP", "TMPDIR", "SYSTEMROOT", "SYSTEMDRIVE", "LANG", "LC_ALL"}
_BASE_ENV = {k: v for k, v in os.environ.items() if k in _SAFE_ENV_KEYS}
_COMPILE_TIMEOUT = int(os.environ.get("COMPILE_TIMEOUT", "30"))
# 실행 바이너리: 512 MB / 컴파일러: 2 GB — Linux(Cloud Run) 전용
_RUN_MEM_LIMIT  = 512 * 1024 * 1024
_COMPILE_MEM_LIMIT = 2 * 1024 * 1024 * 1024
_PROC_LIMIT = 64


def _make_resource_limits(mem_bytes: int):
    """지정 메모리 한도로 subprocess preexec_fn 반환 — Linux 전용."""
    def _set():
        try:
            import resource  # noqa: PLC0415
            resource.setrlimit(resource.RLIMIT_AS, (mem_bytes, mem_bytes))
            resource.setrlimit(resource.RLIMIT_NPROC, (_PROC_LIMIT, _PROC_LIMIT))
        except Exception:
            pass
    return _set if sys.platform != "win32" else None


_PREEXEC_RUN     = _make_resource_limits(_RUN_MEM_LIMIT)
_PREEXEC_COMPILE = _make_resource_limits(_COMPILE_MEM_LIMIT)


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
            preexec_fn=_PREEXEC_RUN,
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
                preexec_fn=_PREEXEC_COMPILE,
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
                preexec_fn=_PREEXEC_RUN,
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
