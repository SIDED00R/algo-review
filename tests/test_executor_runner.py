"""실행기의 자원 상한.

실행이 공개 서비스로 열리면 "제출 코드가 정상적일 것" 이라는 가정이 사라진다. 무한
출력·무한 루프·남는 손자 프로세스는 인스턴스를 통째로 묶어버리므로 실측으로 고정한다.
"""
import io
import os
import pathlib
import subprocess
import tempfile
import time

import pytest

from executor import runner
from executor.runner import _TRUNCATED_NOTICE, MAX_OUTPUT_BYTES, UnsupportedLanguage, run_code


def _py(code, stdin="", timeout=5):
    return run_code("Python 3", code, stdin, timeout)


def test_unknown_language_is_reported_as_such():
    with pytest.raises(UnsupportedLanguage):
        run_code("Rust", "fn main() {}", "", 5)


def test_endless_output_is_truncated_instead_of_filling_memory():
    r = _py("print('x' * 5_000_000)")

    assert r["exit_code"] == 0
    assert "잘렸습니다" in r["stdout"]
    # 잘림 안내를 제외한 본문이 상한을 넘지 않는다.
    assert len(r["stdout"].split(_TRUNCATED_NOTICE)[0].encode()) <= MAX_OUTPUT_BYTES


def test_endless_stderr_is_truncated_too():
    r = _py("import sys; sys.stderr.write('e' * 5_000_000)")

    assert "잘렸습니다" in r["stderr"]


def test_output_under_the_cap_is_untouched():
    r = _py("print('hello')")

    assert r["stdout"] == "hello\n"
    assert "잘렸습니다" not in r["stdout"]


def test_output_exactly_at_the_cap_is_not_marked_truncated():
    r = _py(f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES})")

    assert r["exit_code"] == 0
    assert _TRUNCATED_NOTICE not in r["stdout"]
    assert len(r["stdout"].encode()) == MAX_OUTPUT_BYTES


def test_output_one_byte_over_the_cap_is_marked_truncated():
    r = _py(f"import sys; sys.stdout.write('x' * {MAX_OUTPUT_BYTES + 1})")

    assert r["exit_code"] == 0
    assert _TRUNCATED_NOTICE in r["stdout"]


def test_infinite_loop_is_cut_at_the_timeout():
    start = time.time()
    r = _py("while True: pass", timeout=1)
    elapsed = time.time() - start

    assert r["exit_code"] == -1
    assert "시간 초과" in r["stderr"]
    # 타임아웃 뒤에도 스레드 join 등으로 매달리지 않아야 한다.
    assert elapsed < 10


def test_stdin_larger_than_the_pipe_buffer_does_not_deadlock():
    """파이프 버퍼(리눅스 64KB)보다 큰 입력을 한 번에 write 하면 자식이 읽기 전엔 막힌다."""
    payload = "9\n" * 20_000

    r = _py("import sys; print(len(sys.stdin.read()))", stdin=payload, timeout=5)

    assert r["exit_code"] == 0, r["stderr"]
    assert r["stdout"].strip() == str(len(payload))


def test_exit_code_and_elapsed_time_are_reported():
    r = _py("import sys; print('before'); sys.exit(3)")

    assert r["exit_code"] == 3
    assert r["stdout"].strip() == "before"
    assert isinstance(r["time_ms"], int)


@pytest.mark.skipif(os.name != "posix", reason="프로세스 그룹 종료는 POSIX 경로다")
def test_orphaned_grandchildren_are_killed_with_the_group():
    """자식이 손자를 남기고 먼저 끝나도 손자가 살아남으면 안 된다.

    직접 자식만 kill 하면 손자는 인스턴스 수명 동안 CPU 를 계속 쓴다 — 공개 엔드포인트에서는
    그 자체가 남용 경로다.
    """
    marker = pathlib.Path(tempfile.mkdtemp()) / "grandchild-was-alive"
    code = (
        "import subprocess, sys\n"
        f"subprocess.Popen([sys.executable, '-c', \"import time, pathlib; time.sleep(2);\"\n"
        f"                  \"pathlib.Path({str(marker)!r}).write_text('alive')\"])\n"
        "print('parent done')\n"
    )

    r = _py(code, timeout=5)
    assert r["stdout"].strip() == "parent done", r["stderr"]

    time.sleep(3)
    assert not marker.exists(), "손자 프로세스가 살아남아 파일을 남겼다"


def test_cpp_compile_timeout_returns_the_expected_stderr_and_exit_code(monkeypatch):
    """g++ 컴파일이 시간 초과되면 그룹째 죽이되, 반환 계약(문구·exit_code)은 그대로여야 한다."""

    class _FakeCompileProc:
        def __init__(self):
            self.pid = 999999
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"")
            self._waited = 0

        def wait(self, timeout=None):
            self._waited += 1
            if self._waited == 1:
                raise subprocess.TimeoutExpired(cmd="g++", timeout=timeout)
            return -9

        def kill(self):
            pass

    monkeypatch.setattr(runner, "_spawn", lambda cmd, cwd: _FakeCompileProc())
    kill_calls = []
    monkeypatch.setattr(runner, "_kill_tree", lambda proc, pgid: kill_calls.append(pgid))

    r = runner._run_cpp("int main(){}", b"", timeout=5, compile_timeout=1)

    assert r["stderr"].startswith("[컴파일 시간 초과")
    assert r["exit_code"] == -1
    expected_pgid = 999999 if os.name == "posix" else None
    assert kill_calls == [expected_pgid]


def test_cpp_compile_error_stderr_over_the_cap_is_truncated(monkeypatch):
    """컴파일 실패 stderr 가 상한을 넘으면 잘림 안내가 붙고 길이가 상한 이하여야 한다."""

    class _FakeFailedCompileProc:
        def __init__(self):
            self.pid = 999999
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"e" * (MAX_OUTPUT_BYTES + 10_000))

        def wait(self, timeout=None):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(runner, "_spawn", lambda cmd, cwd: _FakeFailedCompileProc())

    r = runner._run_cpp("int main(){", b"", timeout=5, compile_timeout=5)

    assert "잘렸습니다" in r["stderr"]
    assert len(r["stderr"].split(_TRUNCATED_NOTICE)[0].encode()) <= MAX_OUTPUT_BYTES


def test_cpp_compile_error_stderr_normalizes_crlf(monkeypatch):
    """컴파일 실패 stderr 도 CRLF 를 LF 로 정규화해야 한다."""

    class _FakeFailedCompileProc:
        def __init__(self):
            self.pid = 999999
            self.stdin = io.BytesIO()
            self.stdout = io.BytesIO(b"")
            self.stderr = io.BytesIO(b"a\r\nb\r\n")

        def wait(self, timeout=None):
            return 1

        def kill(self):
            pass

    monkeypatch.setattr(runner, "_spawn", lambda cmd, cwd: _FakeFailedCompileProc())

    r = runner._run_cpp("int main(){", b"", timeout=5, compile_timeout=5)

    assert "\r" not in r["stderr"]
    assert r["stderr"] == "a\nb\n"
