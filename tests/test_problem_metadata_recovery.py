"""solved.ac 일시 장애가 문제 메타데이터를 영구 오염시키지 않는지.

`resolve_problem_info` 는 조회 실패 시 자리표시 메타(제목 "문제 N", 티어 0, 태그 없음)로
리뷰를 진행시킨다. 그 값이 reviews 행으로 저장되고, `db.get_cached_problem_info` 는 가장
최근 리뷰 행을 캐시로 쓴다 — 자리표시를 캐시로 인정하면 solved.ac 가 복구돼도 다시는
조회하지 않는다.

그 상태의 파급은 리뷰 1건이 아니다: 태그 통계·평균 티어·취약 태그가 전부 그 문제를
빠뜨리고, /api/report 는 400 "아직 저장된 기록이 없습니다" 를 낸다. 리뷰 삭제 라우트도
메타 재조회 라우트도 없어 사용자가 복구할 방법이 없다.
"""
from unittest.mock import patch

import pytest

import db
import routes.problem_resolve as pr

_REAL = {"id": 1000, "platform": "boj", "problem_ref": "1000", "title": "A+B",
         "tier": 1, "tier_name": "Bronze V", "tags": ["구현", "사칙연산"]}


def _save(info, efficiency="poor"):
    db.save_review(info["id"], info["title"], info["tier"], info["tags"], "print(1)", "fb",
                   efficiency, platform="boj", problem_ref=info["problem_ref"],
                   tier_name=info["tier_name"], language="Python 3")


def _resolve(side_effect=None, return_value=None):
    kw = {"side_effect": side_effect} if side_effect else {"return_value": dict(return_value)}
    with patch.object(pr.api_client, "get_problem_info", **kw):
        return pr.resolve_problem_info("boj", 1000, None)


def test_a_transient_failure_is_retried_on_the_next_review():
    """자리표시가 캐시로 굳지 않는다 — solved.ac 가 복구되면 다음 리뷰가 실제 메타를 받는다."""
    fallback = _resolve(side_effect=RuntimeError("503"))
    assert fallback["title"] == "문제 1000" and fallback["tier"] == 0
    _save(fallback)

    healed = _resolve(return_value=_REAL)
    assert healed["title"] == "A+B"
    assert healed["tier"] == 1
    assert healed["tags"] == ["구현", "사칙연산"]


def test_rows_saved_during_the_outage_are_repaired():
    """집계 기준은 문제당 **첫 판정 행**이다 — 그 행이 자리표시로 남으면 새 리뷰를 아무리
    해도 그 문제의 태그가 통계에 들어오지 않는다."""
    _save(_resolve(side_effect=RuntimeError("503")))
    assert db.get_tag_stats() == []

    _resolve(return_value=_REAL)          # 복구 — 과거 행을 되살린다
    db.reset_tag_stats_rebuild_flag()
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert set(stats) == {"구현", "사칙연산"}
    assert stats["구현"]["total_count"] == 1
    assert db.get_average_tier() == 1.0


def test_a_real_unrated_problem_is_not_treated_as_a_placeholder():
    """solved.ac 에 실제로 Unrated 로 등록된 문제까지 자리표시로 보면 리뷰마다 재조회한다."""
    unrated = {"id": 1000, "platform": "boj", "problem_ref": "1000",
               "title": "출력만 하기", "tier": 0, "tier_name": "Unrated", "tags": []}
    _save(_resolve(return_value=unrated))

    with patch.object(pr.api_client, "get_problem_info", side_effect=AssertionError("재조회했다")) as spy:
        again = pr.resolve_problem_info("boj", 1000, None)
    assert spy.call_count == 0
    assert again["title"] == "출력만 하기"


def test_the_placeholder_survives_a_still_broken_upstream():
    """복구되지 않았으면 자리표시를 유지한다 — 리뷰 자체는 계속 가능해야 한다."""
    _save(_resolve(side_effect=RuntimeError("503")))
    again = _resolve(side_effect=RuntimeError("still down"))
    assert again["title"] == "문제 1000"
    assert again["platform"] == "boj" and again["problem_ref"] == "1000"


def test_repair_touches_only_the_problem_metadata():
    """제목·티어·태그는 문제의 속성이라 갱신하지만, 제출 코드·판정은 건드리지 않는다."""
    _save(_resolve(side_effect=RuntimeError("503")), efficiency="good")
    _resolve(return_value=_REAL)

    rows = db.get_reviews_by_problem("boj", "1000")
    assert len(rows) == 1
    assert rows[0]["title"] == "A+B"
    assert rows[0]["efficiency"] == "good", "판정이 바뀌었다"
    assert rows[0]["code"] == "print(1)", "제출 코드가 바뀌었다"


@pytest.mark.parametrize("title,tier,tags,expected", [
    ("문제 1000", 0, [], True),
    ("A+B", 0, [], False),          # 실제 Unrated 문제
    ("문제 1000", 1, [], False),     # 티어가 붙었다
    ("문제 999", 0, [], False),      # 다른 문제의 자리표시
])
def test_placeholder_detection_boundaries(title, tier, tags, expected):
    info = {"title": title, "tier": tier, "tags": tags}
    assert pr.is_unresolved_problem_info(info, 1000) is expected
