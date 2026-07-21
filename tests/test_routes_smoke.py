"""DB 만 타는 읽기 라우트의 스모크 테스트.

server.py 의 lifespan(warmup 백그라운드 태스크가 외부 API 를 친다)을 피하려고
대상 라우터만 얹은 최소 앱을 조립한다. 외부 API 호출 경로는 여기서 다루지 않는다.
"""
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

import db
from routes import history, solved, stats


@pytest.fixture
def client():
    app = FastAPI()
    app.include_router(stats.router)
    app.include_router(history.router)
    app.include_router(solved.router)
    return TestClient(app)


def test_stats_boj_empty(client):
    r = client.get("/api/stats", params={"platform": "boj"})
    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "boj"
    assert body["total_reviews"] == 0
    assert body["avg_tier"] == 10.0


def test_stats_codeforces_empty(client):
    r = client.get("/api/stats", params={"platform": "codeforces"})
    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "codeforces"
    assert body["avg_rating"] == 1200.0


def test_stats_rejects_unknown_platform(client):
    r = client.get("/api/stats", params={"platform": "leetcode"})
    assert r.status_code == 400


def test_stats_boj_reflects_saved_review(client):
    db.save_review(problem_id=1, title="문제", tier=12, tags=["dp"],
                   code="x", feedback="f", efficiency="good", problem_ref="1")
    body = client.get("/api/stats", params={"platform": "boj"}).json()
    assert body["total_reviews"] == 1
    assert body["avg_tier"] == 12.0


def test_tier_history_shape(client):
    r = client.get("/api/tier-history")
    assert r.status_code == 200
    assert r.json() == {"history": []}


def test_reviews_grouped_shape(client):
    r = client.get("/api/reviews/grouped")
    assert r.status_code == 200
    assert r.json() == {"problems": []}


def test_solved_history_shape(client):
    r = client.get("/api/solved-history")
    assert r.status_code == 200
    assert r.json() == {"problems": []}
