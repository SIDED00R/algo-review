"""리뷰 대기 등록 라우트 — 외부 API·GitHub 를 타지 않는 경로만 검증한다.

test_routes_smoke.py 와 같은 이유로 대상 라우터만 얹은 최소 앱을 쓴다(server.py lifespan 회피).
"""
import pytest
from fastapi import HTTPException

import db
from routes import pending_review

_PROBLEM_INFO = {
    "id": 1000, "platform": "boj", "problem_ref": "1000",
    "title": "A+B", "tier": 1, "tier_name": "Bronze V", "tags": ["구현"],
}
_BODY = {"platform": "boj", "problem_id": 1000, "code": "print(1)", "language": "Python 3"}


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(pending_review, "resolve_problem_info", lambda *a, **k: _PROBLEM_INFO)
    monkeypatch.setattr(pending_review, "require_github_target", lambda: ("owner/repo", "token"))
    return minimal_app(pending_review.router)


def test_requires_language(minimal_client):
    r = minimal_client.post("/api/review/pending", json={**_BODY, "language": ""})
    assert r.status_code == 400
    assert "언어" in r.json()["detail"]


def test_requires_code(minimal_client):
    r = minimal_client.post("/api/review/pending", json={**_BODY, "code": "   "})
    assert r.status_code == 400


def test_saves_pending_row_after_successful_push(minimal_client, monkeypatch):
    monkeypatch.setattr(pending_review, "push_review_bundle",
                        lambda *a, **k: "백준/Bronze/1000번. A+B")

    body = minimal_client.post("/api/review/pending", json=_BODY).json()
    assert body["pushed"] is True
    assert body["path"] == "백준/Bronze/1000번. A+B"

    rows = db.get_reviews_by_problem("boj", "1000")
    assert len(rows) == 1
    assert rows[0]["efficiency"] == db.PENDING_EFFICIENCY
    assert rows[0]["language"] == "Python 3"


def test_push_failure_leaves_no_row(minimal_client, monkeypatch):
    def _fail(*a, **k):
        raise HTTPException(status_code=500, detail="GitHub push에 실패했습니다.")

    monkeypatch.setattr(pending_review, "push_review_bundle", _fail)

    assert minimal_client.post("/api/review/pending", json=_BODY).status_code == 500
    # 저장소에 없는 유령 기록이 남으면 안 된다.
    assert db.get_reviews_by_problem("boj", "1000") == []
