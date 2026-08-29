"""/api/stats 의 CF 분기 — 기록이 없을 때 가짜 레이팅을 내보내지 않는지.

avg_rating 은 기록이 없어도 추천용 기본값(1200.0)을 돌려준다 — 그대로 표시하면
CF 기록이 없는 사용자에게 "CF 1200" 이 뜬다.
"""
import pytest

from routes import stats


@pytest.fixture
def minimal_client(minimal_app):
    return minimal_app(stats.router)


def test_no_cf_reviews_reports_na_instead_of_a_fake_rating(minimal_client):
    body = minimal_client.get("/api/stats?platform=codeforces").json()
    assert body["avg_tier_name"] == "N/A"
