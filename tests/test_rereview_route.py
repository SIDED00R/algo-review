"""재리뷰 라우트 — 외부 API·LLM 을 타지 않는 경로만 검증한다.

test_routes_smoke.py 와 같은 이유로 대상 라우터만 얹은 최소 앱을 쓴다(server.py lifespan 회피).
GitHub 설정 테이블이 비어 있으므로 push 는 항상 pushed=false 로 떨어진다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from routes import rereview


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(rereview.router)
    return TestClient(app)


def _save(efficiency, **kw):
    args = {
        "problem_id": 1000, "title": "A+B", "tier": 1, "tags": ["구현"],
        "code": "print(1)", "feedback": "", "efficiency": efficiency,
        "problem_ref": "1000", "language": "Python 3",
    }
    args.update(kw)
    db.save_review(**args)


def test_rejects_unknown_platform(client):
    assert client.post("/api/rereview/leetcode/1000").status_code == 400


def test_missing_record_returns_404(client):
    assert client.post("/api/rereview/boj/1000").status_code == 404


def test_reviewed_row_skips_llm_and_reports_push_failure(client, monkeypatch):
    _save("good", feedback="f")
    monkeypatch.setattr(rereview.analyzer, "analyze_code",
                        lambda *a, **k: pytest.fail("이미 리뷰된 행에서 LLM 을 호출하면 안 된다"))

    body = client.post("/api/rereview/boj/1000").json()
    assert body["reviewed"] is False
    assert body["pushed"] is False  # GitHub 미연결
    assert "GitHub" in body["detail"]


def test_pending_row_is_filled_by_review(client, monkeypatch):
    _save(db.PENDING_EFFICIENCY)
    monkeypatch.setattr(rereview.settings, "openai_api_key", "test-key")
    monkeypatch.setattr(rereview, "resolve_statement", lambda *a, **k: "문제 본문")
    monkeypatch.setattr(rereview.analyzer, "analyze_code", lambda *a, **k: {
        "efficiency": "ok", "complexity": "O(N)", "better_algorithm": None,
        "feedback": "피드백", "strengths": [], "weaknesses": [],
    })

    body = client.post("/api/rereview/boj/1000").json()
    assert body["reviewed"] is True
    saved = db.get_reviews_by_problem("boj", "1000")
    assert len(saved) == 1  # 회차가 늘지 않는다
    assert saved[0]["efficiency"] == "ok"
    assert saved[0]["complexity"] == "O(N)"


def test_pending_row_without_api_key_returns_400(client, monkeypatch):
    _save(db.PENDING_EFFICIENCY)
    monkeypatch.setattr(rereview.settings, "openai_api_key", "")

    r = client.post("/api/rereview/boj/1000")
    assert r.status_code == 400
    # 리뷰는 여전히 대기 상태로 남는다 — 나중에 다시 시도할 수 있다.
    assert db.get_reviews_by_problem("boj", "1000")[0]["efficiency"] == db.PENDING_EFFICIENCY
