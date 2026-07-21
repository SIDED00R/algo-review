"""헬스체크 엔드포인트 + 전역 예외 핸들러 (server.app 전체를 통해 검증)."""
import pytest
from fastapi.testclient import TestClient
from sqlalchemy.exc import OperationalError

import db
import server
import warmup


@pytest.fixture
def client(monkeypatch):
    # lifespan 의 warmup 백그라운드 태스크(외부 API)를 no-op 으로 막는다.
    async def _noop():
        return None

    monkeypatch.setattr(warmup, "warm_theme_caches", _noop)
    with TestClient(server.app) as c:
        yield c


def test_healthz_returns_200_with_db_ok(client):
    r = client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["db"] == "ok"


def test_db_operational_error_maps_to_503(client, monkeypatch):
    def _boom(*args, **kwargs):
        raise OperationalError("SELECT 1", {}, Exception("connection refused"))

    # /api/stats 가 타는 첫 db 호출을 강제로 실패시킨다.
    monkeypatch.setattr(db, "get_review_history", _boom)
    r = client.get("/api/stats", params={"platform": "boj"})
    assert r.status_code == 503
    assert "데이터베이스" in r.json()["detail"]
