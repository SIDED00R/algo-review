"""추천 검색 실패가 "기록 없음"으로 위장되지 않는지 (회귀, #113).

운영에서 solved.ac 가 Cloud Run 을 403 으로 막는 동안 /api/recommend?platform=boj 는
`recommendations: []` 를 돌려주고, 프론트는 "아직 추천 데이터가 없습니다. 먼저 코드
리뷰를 몇 개 진행해보세요." 로 **사용자를 탓했다** — 같은 응답에 avg_tier 8.9 와 취약
태그 5개가 채워져 있는데도.

검색기가 전면 실패를 빈 목록으로 돌려주면 호출부가 "조건에 맞는 문제 없음" 과 구분할 수
없다. themes 응답이 이미 쓰던 error 필드 계약을 recommend 에도 준다.
"""
import pytest
import requests

import db
from clients import ProblemSearchError, solved_ac
from routes import recommend

_BOJ = dict(problem_id=1000, title="A+B", tier=8, tags=["math"],
            code="print(1)", feedback="f", efficiency="poor",
            platform="boj", problem_ref="1000", tier_name="Silver III")


@pytest.fixture
def minimal_client(monkeypatch, minimal_app):
    monkeypatch.setattr(recommend, "IS_DEMO", False)
    return minimal_app(recommend.router)


class _Blocked:
    """solved.ac 가 Cloud Run 을 막을 때의 실제 응답(403)."""
    status_code = 403
    ok = False

    def raise_for_status(self):
        raise requests.HTTPError("403 Client Error: Forbidden")

    def json(self):
        return {}


def test_search_transport_failure_raises_instead_of_returning_empty(monkeypatch):
    monkeypatch.setattr(solved_ac.requests, "get", lambda *a, **k: _Blocked())
    with pytest.raises(ProblemSearchError):
        solved_ac.search_problems_by_tag("math", 1, 5, exclude_ids=set())


def test_route_reports_the_failure_instead_of_blaming_the_user(minimal_client, monkeypatch):
    db.save_review(**_BOJ)
    monkeypatch.setattr(solved_ac.requests, "get", lambda *a, **k: _Blocked())

    body = minimal_client.get("/api/recommend?platform=boj").json()

    assert body["recommendations"] == []
    assert body["error"], "검색 실패를 알리는 error 필드가 없다"
    # 실패했어도 사용자 데이터는 그대로 내려간다 — 이 조합이 "기록 없음" 오해의 근원이다.
    assert body["weak_tags"], "취약 태그는 DB 에서 나오므로 실패와 무관하다"
    assert body["avg_tier"] > 0


def test_genuinely_empty_result_has_no_error(minimal_client, monkeypatch):
    """실패가 아니라 정말 조건에 맞는 문제가 없는 경우 — 여기에는 error 가 없어야 한다."""
    db.save_review(**_BOJ)
    monkeypatch.setattr(recommend.recommender, "get_recommendations", lambda *a, **k: [])

    body = minimal_client.get("/api/recommend?platform=boj").json()

    assert body["recommendations"] == []
    assert body["error"] == ""


def test_no_records_still_short_circuits(minimal_client):
    """기록이 아예 없으면 취약 태그가 없어 검색 자체를 하지 않는다."""
    body = minimal_client.get("/api/recommend?platform=boj").json()
    assert body["weak_tags"] == [] and body["recommendations"] == []
