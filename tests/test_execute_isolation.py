"""코드 실행 격리 (회귀).

ARCHITECTURE.md 는 "subprocess 실행 시 _SAFE_ENV_KEYS 만 허용 → API 키 환경변수 노출 차단"
이라고 적었지만, cwd 를 지정하지 않아 서버의 작업 디렉터리를 상속했다. sys.path[0] 가 리포
루트가 되므로 제출 코드가 `import config` 로 .env 를 읽을 수 있었다(config 의 env_file 은
CWD 상대 경로다). 운영은 .dockerignore + non-root 로 막히지만, 문서의 주장이 실제보다 강했다.
"""
import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import execute as execute_route
from routes.execute import _run_python, safe_env


def test_submitted_code_cannot_import_project_modules():
    r = _run_python("import config; print('LEAK')", "", 5)

    assert r["exit_code"] != 0
    assert "LEAK" not in r["stdout"]
    assert "ModuleNotFoundError" in r["stderr"] or "No module named" in r["stderr"]


def test_submitted_code_does_not_run_in_the_repo_directory():
    r = _run_python("import os; print(os.getcwd())", "", 5)

    assert r["exit_code"] == 0
    assert os.path.abspath(r["stdout"].strip()) != os.path.abspath(os.getcwd())


@pytest.mark.parametrize("key", ["OPENAI_API_KEY", "DB_PASSWORD", "GITHUB_CLIENT_SECRET",
                                 "CODEFORCES_API_SECRET", "CODEFORCES_PASSWORD"])
def test_secret_environment_variables_do_not_reach_the_subprocess(monkeypatch, key):
    """실제로 심은 센티넬이 새지 않는지 본다.

    예전 버전은 "이 키들이 stdout 에 없다" 만 단정했는데, 로컬·CI 환경에 그 키가 애초에
    없어서(pydantic-settings 는 .env 를 파일에서 읽고 os.environ 에 넣지 않는다) 필터를
    통째로 지워도 통과했다 — 변이로 확인한 거짓 초록이다. 이제 센티넬을 심고,
    safe_env() 가 호출 시점에 필터하므로 그 값이 실제로 반영된다.
    """
    monkeypatch.setenv(key, "sentinel-must-not-leak")

    assert key not in safe_env()   # 필터 자체
    r = _run_python(f"import os; print(os.environ.get({key!r}, ''))", "", 5)

    assert r["exit_code"] == 0
    assert "sentinel-must-not-leak" not in r["stdout"]


def test_safe_keys_do_reach_the_subprocess(monkeypatch):
    """필터가 과하면 정상 실행이 깨진다 — 허용 키는 통과해야 한다."""
    monkeypatch.setenv("LANG", "ko_KR.UTF-8")

    assert safe_env().get("LANG") == "ko_KR.UTF-8"


def test_normal_code_still_runs():
    """격리가 정상 실행을 막지 않아야 한다 — 표준 라이브러리는 쓸 수 있다."""
    r = _run_python("import sys, math, collections\nprint(math.gcd(12, 18), input())",
                    "hello", 5)

    assert r["exit_code"] == 0
    assert r["stdout"].strip() == "6 hello"


# ── 엔드포인트 게이트 (회귀) ──
#
# 운영 서비스는 allUsers 공개이고 앱에는 인증이 없다. 자식 프로세스가 앱과 같은 uid·같은
# 네트워크 네임스페이스에서 도는 한, 환경변수 필터·cwd 격리·-I 로도 두 경로가 남는다:
#   ① 네트워크 egress → GCE 메타데이터 서버 → 런타임 SA 액세스 토큰
#   ② /proc/1/environ → 앱 프로세스의 환경변수 전체
# 그래서 엔드포인트 자체를 기본 비활성으로 둔다.

_REQ = {"code": "print(1)", "language": "Python 3", "stdin": "", "timeout_sec": 5}


def _client():
    """conftest 의 minimal_app 과 같은 최소 앱 — 여기서는 픽스처가 아니라 함수여야 한다
    (monkeypatch 를 먼저 적용한 뒤 만들어야 하는 테스트가 있다)."""
    app = FastAPI()
    app.include_router(execute_route.router)
    return TestClient(app)


def test_endpoint_is_disabled_by_default(monkeypatch):
    monkeypatch.setattr(execute_route.settings, "execute_enabled", False)
    monkeypatch.setattr(execute_route, "_run_python",
                        lambda *a, **k: pytest.fail("게이트가 닫혀 있으면 실행하면 안 된다"))

    resp = _client().post("/api/execute", json=_REQ)

    assert resp.status_code == 403
    assert "EXECUTE_ENABLED" in resp.json()["detail"]


def test_endpoint_runs_when_explicitly_enabled(monkeypatch):
    monkeypatch.setattr(execute_route.settings, "execute_enabled", True)

    resp = _client().post("/api/execute", json=_REQ)

    assert resp.status_code == 200
    assert resp.json()["stdout"].strip() == "1"


def test_demo_mode_blocks_even_when_enabled(monkeypatch):
    """데모 가드가 게이트보다 먼저다 — 데모에 EXECUTE_ENABLED 가 켜져도 막힌다."""
    monkeypatch.setattr(execute_route, "IS_DEMO", True)
    monkeypatch.setattr(execute_route.settings, "execute_enabled", True)
    monkeypatch.setattr(execute_route, "_run_python",
                        lambda *a, **k: pytest.fail("데모에서 실행하면 안 된다"))

    assert _client().post("/api/execute", json=_REQ).status_code == 403


# ── UTF-8 출력 (회귀) ──
#
# `-I`(isolated)는 `-E` 를 포함해 **모든 PYTHON* 환경변수를 무시**한다. 그래서
# PYTHONIOENCODING/PYTHONUTF8 를 env 로 넘겨도 적용되지 않았고, 비-ASCII 를 출력하는
# 제출 코드가 Windows 에서 UnicodeEncodeError 로 죽었다. 커맨드라인 플래그로 줘야 한다.

@pytest.mark.parametrize("text", ["안녕하세요", "你好世界", "Привет", "😀🎉", "café"])
def test_non_ascii_output_survives(text):
    r = _run_python(f"print({text!r})", "", 8)

    assert r["exit_code"] == 0, r["stderr"]
    assert text in r["stdout"]


def test_child_stdout_is_utf8():
    r = _run_python("import sys; print(sys.stdout.encoding)", "", 8)

    assert r["exit_code"] == 0
    assert r["stdout"].strip().lower().replace("-", "") == "utf8"


def test_non_ascii_stdin_is_readable():
    r = _run_python("print(input()[::-1])", "가나다", 8)

    assert r["exit_code"] == 0
    assert r["stdout"].strip() == "다나가"


def test_output_is_unbuffered_enough_to_survive_a_crash():
    """-u 가 없으면 버퍼에 남은 출력이 비정상 종료에 유실된다."""
    r = _run_python("import sys; print('before'); sys.exit(3)", "", 8)

    assert r["exit_code"] == 3
    assert "before" in r["stdout"]
