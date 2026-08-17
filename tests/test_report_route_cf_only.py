"""CF 기록만 있는 사용자의 /api/report (회귀).

tag_stats() 는 BOJ 첫 제출에만 집계된다 — 수정 전에는 CF 리뷰가 아무리 많아도
"아직 저장된 기록이 없습니다"(400)를 받았다. CF 기록만 있으면 get_cf_tag_stats() 로 분기해야 한다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from routes import report

_CF_KW = dict(
    problem_id=0, title="Watermelon", tier=0, tags=["math"],
    code="print(1)", feedback="f", efficiency="good",
    platform="codeforces", problem_ref="4A", tier_name="Codeforces 800",
)


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(report.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(report.analyzer, "get_cumulative_analysis", lambda *a, **k: "리포트 본문")
    app = FastAPI()
    app.include_router(report.router)
    return TestClient(app)


def test_cf_only_history_is_not_400(client):
    db.save_review(**_CF_KW)

    r = client.get("/api/report")

    assert r.status_code == 200
    assert r.json()["report"] == "리포트 본문"
