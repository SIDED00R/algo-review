"""추천 검색 실패가 "기록 없음"으로 위장되지 않는지.

solved.ac 가 Cloud Run 을 403 으로 막으면 /api/recommend?platform=boj 는 검색만 실패한다.
그때 빈 목록을 돌려주면 프론트는 "아직 추천 데이터가 없습니다. 먼저 코드 리뷰를 몇 개
진행해보세요." 로 **사용자를 탓하게 된다** — 같은 응답에 avg_tier 와 취약 태그가 채워져
있는데도.

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


def test_no_graded_tier_reports_na_instead_of_a_fake_tier(minimal_client):
    """등급 있는 기록이 없으면 avg_tier 는 추천용 기본값(10.0)이다 — 그대로 표시하면
    기록이 없는 사용자에게 "Silver I" 가 뜬다."""
    body = minimal_client.get("/api/recommend?platform=boj").json()
    assert body["tier_name"] == "N/A"


def test_no_graded_tier_has_zero_avg_tier_and_dash_range(minimal_client):
    """등급 있는 기록이 없으면 응답의 avg_tier 는 0, tier_range 는 "-" 다."""
    body = minimal_client.get("/api/recommend?platform=boj").json()
    assert body["avg_tier"] == 0
    assert body["tier_range"] == "-"


def test_graded_tier_present_shows_real_avg_tier_and_range(minimal_client):
    """등급 있는 리뷰가 있으면 avg_tier 는 0 이 아니고 tier_range 도 채워진다."""
    db.save_review(**_BOJ)

    body = minimal_client.get("/api/recommend?platform=boj").json()

    assert body["avg_tier"] > 0
    assert body["tier_range"] != "-"


def test_recommendation_band_uses_raw_avg_not_display_value(minimal_client, monkeypatch):
    """등급 없는 상태에서도 추천 밴드는 표시용 0 이 아니라 원래 기본값(10.0)으로 계산돼야
    한다 — avg_tier 를 표시값으로 재대입하면 밴드가 Bronze 대(1~2)로 무너진다."""
    monkeypatch.setattr(recommend.recommender, "get_weak_tags_scored", lambda *a, **k: ["math"])
    monkeypatch.setattr(recommend.recommender, "get_tag_key_by_name", lambda t: t)

    seen_bands = []

    def _search(tag_key, min_tier, max_tier, exclude_ids):
        seen_bands.append((min_tier, max_tier))
        return []

    monkeypatch.setattr(recommend.recommender, "search_problems_by_tag", _search)

    minimal_client.get("/api/recommend?platform=boj")

    assert seen_bands, "search_problems_by_tag 가 호출되지 않았다"
    # avg=10.0(기본값) 기준 same 밴드는 (9, 12) — Gold V ~ Gold III.
    # avg=0(표시값)이 새어 들어가면 (1, 2) — Bronze V ~ Bronze IV 로 무너진다.
    assert seen_bands[0] == (9, 12), f"밴드가 표시값(0)으로 계산됐다: {seen_bands[0]}"


def test_one_tag_failure_does_not_discard_the_others(minimal_client, monkeypatch):
    """태그별로 실패를 격리한다 — 첫 실패에서 던지면 이미 성공한 태그의 결과까지 버린다.

    태그마다 별도 HTTP 호출이므로 한 태그의 실패가 나머지를 무효로 만들 이유가 없다.
    """
    db.save_review(**_BOJ)
    # 취약 태그 목록은 이 테스트의 관심사가 아니다 — 두 개로 고정한다.
    monkeypatch.setattr(recommend.recommender, "get_weak_tags_scored",
                        lambda *a, **k: ["math", "dp"])

    calls = {"n": 0}

    def _search(tag_key, min_tier, max_tier, exclude_ids):
        calls["n"] += 1
        # same/hard 밴드가 각자 try/except 로 격리되므로 same 밴드가 실패해도 같은 태그의
        # hard 밴드 호출은 그대로 이어진다 — 두 밴드 모두 실패해야 그 태그가 실패로 세어진다.
        # 여기서는 첫 호출(첫 태그의 same 밴드)만 실패시킨다.
        if calls["n"] == 1:
            raise ProblemSearchError("일시적 실패")
        return [{"id": 1000 + calls["n"], "title": "T", "tier": 5, "tier_name": "Bronze I"}]

    monkeypatch.setattr(recommend.recommender, "search_problems_by_tag", _search)
    monkeypatch.setattr(recommend.recommender, "get_tag_key_by_name", lambda t: t)

    body = minimal_client.get("/api/recommend?platform=boj").json()

    assert body["error"] == "", "일부 실패인데 전면 실패로 보고했다"
    assert body["recommendations"], "성공한 태그의 결과까지 버렸다"


def test_all_tags_failing_is_still_reported_as_failure(minimal_client, monkeypatch):
    """부분 실패를 살리느라 전면 실패까지 조용해지면 안 된다."""
    db.save_review(**_BOJ)

    def _search(**kwargs):
        raise ProblemSearchError("solved.ac 문제 검색에 실패했습니다.")

    monkeypatch.setattr(recommend.recommender, "search_problems_by_tag", _search)
    monkeypatch.setattr(recommend.recommender, "get_tag_key_by_name", lambda t: t)

    body = minimal_client.get("/api/recommend?platform=boj").json()

    assert body["error"], "전부 실패했는데 error 가 없다"
    assert body["recommendations"] == []
