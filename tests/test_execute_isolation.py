"""코드 실행 격리 (회귀).

ARCHITECTURE.md 는 "subprocess 실행 시 _SAFE_ENV_KEYS 만 허용 → API 키 환경변수 노출 차단"
이라고 적었지만, cwd 를 지정하지 않아 서버의 작업 디렉터리를 상속했다. sys.path[0] 가 리포
루트가 되므로 제출 코드가 `import config` 로 .env 를 읽을 수 있었다(config 의 env_file 은
CWD 상대 경로다). 운영은 .dockerignore + non-root 로 막히지만, 문서의 주장이 실제보다 강했다.
"""
import os

from routes.execute import _BASE_ENV, _run_python


def test_submitted_code_cannot_import_project_modules():
    r = _run_python("import config; print('LEAK')", "", 5)

    assert r["exit_code"] != 0
    assert "LEAK" not in r["stdout"]
    assert "ModuleNotFoundError" in r["stderr"] or "No module named" in r["stderr"]


def test_submitted_code_does_not_run_in_the_repo_directory():
    r = _run_python("import os; print(os.getcwd())", "", 5)

    assert r["exit_code"] == 0
    assert os.path.abspath(r["stdout"].strip()) != os.path.abspath(os.getcwd())


def test_environment_is_filtered_to_safe_keys():
    r = _run_python("import os; print(sorted(os.environ))", "", 5)

    assert r["exit_code"] == 0
    for leaked in ("OPENAI_API_KEY", "DB_PASSWORD", "GITHUB_CLIENT_SECRET",
                   "CODEFORCES_API_SECRET"):
        assert leaked not in r["stdout"]
    assert "OPENAI_API_KEY" not in _BASE_ENV


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

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from routes import execute as execute_route

_REQ = {"code": "print(1)", "language": "Python 3", "stdin": "", "timeout_sec": 5}


def _client():
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
