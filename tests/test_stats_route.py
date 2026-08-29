"""/api/stats 의 CF 분기 — 기록이 없을 때 가짜 레이팅을 내보내지 않는지.

avg_rating 은 기록이 없어도 추천용 기본값(1200.0)을 돌려준다 — 그대로 표시하면
CF 기록이 없는 사용자에게 "CF 1200" 이 뜬다.
"""
import pytest

import db
from routes import stats


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app(stats.router)


def test_no_cf_reviews_reports_na_instead_of_a_fake_rating(minimal_client):
    body = minimal_client.get("/api/stats?platform=codeforces").json()
    assert body["avg_tier_name"] == "N/A"


def test_unrated_cf_reviews_report_na_instead_of_a_fake_rating(minimal_client):
    """CF 리뷰가 있어도 전부 Unrated 면 avg_tier_name 은 "N/A" 다 — 그러지 않으면
    get_average_cf_rating() 의 기본값(1200.0)이 "CF 1200" 으로 표시된다."""
    db.save_review(problem_id=1, title="A", tier=0, tags=[], code="print(1)",
                   feedback="f", efficiency="poor", platform="codeforces",
                   problem_ref="1A", tier_name="Codeforces Unrated")

    body = minimal_client.get("/api/stats?platform=codeforces").json()

    assert body["avg_tier_name"] == "N/A"


def test_rated_cf_review_reports_the_parsed_rating(minimal_client):
    db.save_review(problem_id=1, title="A", tier=0, tags=[], code="print(1)",
                   feedback="f", efficiency="poor", platform="codeforces",
                   problem_ref="1A", tier_name="Codeforces 1600")

    body = minimal_client.get("/api/stats?platform=codeforces").json()

    assert body["avg_tier_name"] == "CF 1600"


def test_stale_rated_submission_used_when_latest_resubmission_is_unrated(minimal_client, at_time):
    """같은 문제의 최신 회차가 Unrated 여도 평균 레이팅은 이전 레이팅 회차의 값을 쓴다."""
    at_time("2024-01-01T00:00:00")
    db.save_review(problem_id=1, title="A", tier=0, tags=[], code="print(1)",
                   feedback="f", efficiency="poor", platform="codeforces",
                   problem_ref="4A", tier_name="Codeforces 1600")
    at_time("2024-01-02T00:00:00")
    db.save_review(problem_id=1, title="A", tier=0, tags=[], code="print(1)",
                   feedback="f", efficiency="poor", platform="codeforces",
                   problem_ref="4A", tier_name="Codeforces Unrated")

    assert db.get_average_cf_rating() == 1600.0

    body = minimal_client.get("/api/stats?platform=codeforces").json()
    assert body["avg_tier_name"] != "CF 1200"
    assert body["avg_tier_name"] == "CF 1600"


def test_has_cf_rating_is_false_on_an_empty_db():
    assert db.has_cf_rating() is False


def test_has_cf_rating_is_true_once_a_rated_cf_review_exists():
    db.save_review(problem_id=1, title="A", tier=0, tags=[], code="print(1)",
                   feedback="f", efficiency="poor", platform="codeforces",
                   problem_ref="1A", tier_name="Codeforces 1600")

    assert db.has_cf_rating() is True
