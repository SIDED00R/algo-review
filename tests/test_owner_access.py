"""소유자 열쇠 — 판정 규칙, 등록 라우트의 쿠키, 미들웨어가 워커 스레드까지 판정을 전하는지."""
import asyncio

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import owner_access
from owner_access import COOKIE_NAME, OwnerContextMiddleware, is_owner_request, key_matches
from routes import owner

_KEY = "a" * 64


@pytest.fixture(autouse=True)
def owner_key(monkeypatch):
    monkeypatch.setattr(owner_access.settings, "owner_key", _KEY)


@pytest.mark.parametrize("candidate, expected", [
    (_KEY, True),
    ("b" * 64, False),
    ("", False),
    ("열쇠", False),   # compare_digest 는 non-ASCII 에 TypeError — 판정은 False 여야 한다
])
def test_key_matches(candidate, expected):
    assert key_matches(candidate) is expected


def test_unset_key_matches_nothing(monkeypatch):
    monkeypatch.setattr(owner_access.settings, "owner_key", "")
    assert key_matches("") is False
    assert key_matches(_KEY) is False


def test_register_sets_a_strict_httponly_cookie(minimal_app):
    r = minimal_app(owner.router).post("/api/owner/key", json={"key": _KEY})
    assert r.status_code == 200, r.text
    cookie = r.headers["set-cookie"]
    assert cookie.startswith(f"{COOKIE_NAME}={_KEY};")
    assert "HttpOnly" in cookie
    assert "SameSite=strict" in cookie
    assert "Max-Age=31536000" in cookie


@pytest.mark.parametrize("key", ["b" * 64, "열쇠"])
def test_register_rejects_a_wrong_key_without_a_cookie(minimal_app, key):
    r = minimal_app(owner.router).post("/api/owner/key", json={"key": key})
    assert r.status_code == 403
    assert "set-cookie" not in r.headers


def test_register_is_blocked_in_demo(minimal_app, monkeypatch):
    monkeypatch.setattr(owner, "IS_DEMO", True)
    r = minimal_app(owner.router).post("/api/owner/key", json={"key": _KEY})
    assert r.status_code == 403
    assert "[데모]" in r.json()["detail"]


def _probe_app():
    """동기 라우터(스레드풀)와 asyncio.to_thread 양쪽에서 판정이 보이는지 보는 앱."""
    app = FastAPI()
    app.add_middleware(OwnerContextMiddleware)

    @app.get("/sync")
    def _sync():
        return {"owner": is_owner_request()}

    @app.get("/thread")
    async def _thread():
        return {"owner": await asyncio.to_thread(is_owner_request)}

    return TestClient(app)


@pytest.mark.parametrize("path", ["/sync", "/thread"])
@pytest.mark.parametrize("cookie, expected", [(_KEY, True), ("b" * 64, False), (None, False)])
def test_middleware_carries_the_verdict_into_worker_threads(path, cookie, expected):
    client = _probe_app()
    if cookie is not None:
        client.cookies.set(COOKIE_NAME, cookie)
    assert client.get(path).json() == {"owner": expected}


def test_server_app_marks_owner_requests(client, monkeypatch):
    """server.app 에 미들웨어가 실제로 걸려 있어야 리뷰·번역이 Claude 로 간다."""
    import analyzer

    seen = []
    monkeypatch.setattr(analyzer, "claude_answer", lambda s, u: seen.append(is_owner_request()) or "리포트")
    monkeypatch.setattr("routes.report.require_openai_key", lambda *a, **k: None)
    monkeypatch.setattr("routes.report.db.get_tag_stats",
                        lambda *a, **k: [{"tag": "dp", "total_count": 1, "good_count": 1, "poor_count": 0}])
    monkeypatch.setattr("routes.report.db.get_review_history", lambda *a, **k: [])

    client.cookies.set(COOKIE_NAME, _KEY)
    assert client.get("/api/report").status_code == 200
    client.cookies.clear()
    assert client.get("/api/report").status_code == 200
    assert seen == [True, False]
