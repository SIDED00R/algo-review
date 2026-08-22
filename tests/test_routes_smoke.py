"""DB 만 타는 읽기 라우트의 스모크 테스트.

server.py 의 lifespan(warmup 백그라운드 태스크가 외부 API 를 친다)을 피하려고
대상 라우터만 얹은 최소 앱을 조립한다. 외부 API 호출 경로는 여기서 다루지 않는다.
"""
import pytest

import db
from routes import history, solved, stats


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app(stats.router, history.router, solved.router)


def test_stats_boj_empty(minimal_client):
    """등급 있는 기록이 없으면 평균 티어를 표시하지 않는다.

    `get_average_tier` 의 10.0 은 추천 난이도의 기본값이지 표시값이 아니다 — 그대로
    내보내면 기록이 하나도 없는 사용자 화면에 "Silver I" 가 뜬다.
    """
    r = minimal_client.get("/api/stats", params={"platform": "boj"})
    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "boj"
    assert body["total_reviews"] == 0
    assert body["avg_tier"] == 0
    assert body["avg_tier_name"] == "N/A"


def test_stats_codeforces_empty(minimal_client):
    r = minimal_client.get("/api/stats", params={"platform": "codeforces"})
    assert r.status_code == 200
    body = r.json()
    assert body["platform"] == "codeforces"
    assert body["avg_tier_name"] == "CF 1200"   # 기록이 없을 때의 기본 레이팅


def test_stats_rejects_unknown_platform(minimal_client):
    r = minimal_client.get("/api/stats", params={"platform": "leetcode"})
    assert r.status_code == 400


def test_stats_boj_reflects_saved_review(minimal_client):
    db.save_review(problem_id=1, title="문제", tier=12, tags=["dp"],
                   code="x", feedback="f", efficiency="good", problem_ref="1")
    body = minimal_client.get("/api/stats", params={"platform": "boj"}).json()
    assert body["total_reviews"] == 1
    assert body["avg_tier"] == 12.0


def test_tier_history_shape(minimal_client):
    r = minimal_client.get("/api/tier-history")
    assert r.status_code == 200
    assert r.json() == {"history": []}


def test_reviews_grouped_shape(minimal_client):
    r = minimal_client.get("/api/reviews/grouped")
    assert r.status_code == 200
    # total 은 페이저가 읽는다 — 빠지면 프론트가 페이지 수를 못 세고 1페이지에 갇힌다.
    assert r.json() == {"problems": [], "total": 0}


def test_solved_history_shape(minimal_client):
    r = minimal_client.get("/api/solved-history")
    assert r.status_code == 200
    assert r.json() == {"problems": [], "total": 0}
