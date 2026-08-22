"""증분 집계(`_bump_tag_stats`)를 **표에서 직접** 읽어 고정한다.

`db.get_tag_stats()` 로 확인하면 이 경로가 검증되지 않는다 — 그 함수는 표를 주기적으로
**전면 재계산**하므로, 증분 로직을 통째로 없애도 읽는 값이 맞는다(실측: `_bump_tag_stats`
를 no-op 으로 바꿔도 관련 테스트 18건 중 1건만 깨졌다). 운영에서는 재계산에 60초 쿨다운이
있어, 그 사이 사용자가 보는 값은 **증분 결과**다. 그래서 이 파일은 재계산을 거치지 않는
읽기로 증분만 본다.
"""
import db
from db.connection import session_scope
from db.models import TagStat
from sqlalchemy import select


def raw_tag_stats() -> dict:
    """tag_stats 표를 그대로 읽는다 — 재계산을 타지 않는다."""
    with session_scope() as session:
        return {r.tag: {"good": r.good_count, "poor": r.poor_count, "total": r.total_count}
                for r in session.scalars(select(TagStat)).all()}


def mk_review(**kw):
    args = {
        "problem_id": 1, "title": "문제", "tier": 10, "tags": ["dp"],
        "code": "print(1)", "feedback": "f", "efficiency": "good",
        "platform": "boj", "problem_ref": "1", "tier_name": "",
    }
    args.update(kw)
    db.save_review(**args)


def test_first_boj_submission_increments_the_table():
    mk_review(tags=["dp", "greedy"], efficiency="good")
    stats = raw_tag_stats()
    assert stats["dp"] == {"good": 1, "poor": 0, "total": 1}
    assert stats["greedy"] == {"good": 1, "poor": 0, "total": 1}


def test_poor_counts_separately():
    mk_review(tags=["dp"], efficiency="poor")
    assert raw_tag_stats()["dp"] == {"good": 0, "poor": 1, "total": 1}


def test_anything_other_than_good_counts_as_poor():
    """'보통(ok)' 도 poor 로 센다 — good 이 아닌 것은 전부 poor 다.

    증분(`_bump_tag_stats`)과 전면 재계산(`_tally_tag_efficiency`)이 **같은 규칙**이라
    재계산 전후로 값이 흔들리지 않는다. 그 일치가 이 테스트의 요점이다.
    """
    mk_review(tags=["dp"], efficiency="ok")
    assert raw_tag_stats()["dp"] == {"good": 0, "poor": 1, "total": 1}

    db.reset_tag_stats_rebuild_flag()
    rebuilt = {s["tag"]: s for s in db.get_tag_stats()}
    assert rebuilt["dp"]["poor_count"] == 1


def test_resubmission_does_not_increment(at_time):
    at_time("2026-01-01T00:00:00")
    mk_review(tags=["dp"], efficiency="good")
    at_time("2026-01-02T00:00:00")
    mk_review(tags=["dp"], efficiency="poor")
    # 한 문제는 한 번만 센다 — 재제출로 통계가 부풀면 취약 태그 순위가 흔들린다.
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 0, "total": 1}


def test_pending_does_not_increment():
    """판정이 없는 대기 행을 세면 통계가 poor 쪽으로 왜곡된다."""
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    assert raw_tag_stats() == {}


def test_codeforces_does_not_increment():
    """tag_stats 는 BOJ 전용이다 — CF 태그는 별도 경로로 센다."""
    mk_review(platform="codeforces", problem_ref="4A", tags=["math"],
              tier=0, tier_name="Codeforces 800")
    assert raw_tag_stats() == {}


def test_filling_a_pending_round_increments_once(at_time):
    """대기로 올린 뒤 나중에 리뷰를 채우면, 미뤘던 첫 집계가 그때 수행된다."""
    at_time("2026-01-01T00:00:00")
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    target = db.get_reviews_by_problem("boj", "1")[0]["id"]
    assert raw_tag_stats() == {}

    db.update_pending_review("boj", "1", {"efficiency": "good"}, review_id=target)
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 0, "total": 1}


def test_filling_a_pending_round_of_an_already_reviewed_problem_does_not_increment(at_time):
    """이미 리뷰된 문제의 대기 회차를 채우는 것은 재제출이다 — 다시 세면 안 된다."""
    at_time("2026-01-01T00:00:00")
    mk_review(tags=["dp"], efficiency="good")
    at_time("2026-01-02T00:00:00")
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    target = db.get_reviews_by_problem("boj", "1")[0]["id"]

    db.update_pending_review("boj", "1", {"efficiency": "poor"}, review_id=target)
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 0, "total": 1}


def test_two_pending_rounds_fill_to_one_count(at_time):
    """대기 회차가 둘이어도 그 문제는 한 번만 센다."""
    at_time("2026-01-01T00:00:00")
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    first = db.get_reviews_by_problem("boj", "1")[0]["id"]
    at_time("2026-01-02T00:00:00")
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    second = db.get_reviews_by_problem("boj", "1")[0]["id"]

    db.update_pending_review("boj", "1", {"efficiency": "good"}, review_id=first)
    db.update_pending_review("boj", "1", {"efficiency": "poor"}, review_id=second)
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 0, "total": 1}


def test_a_refused_fill_does_not_increment(at_time):
    """선점에 진 요청은 아무것도 바꾸지 않는다 — 집계도 건드리면 안 된다."""
    at_time("2026-01-01T00:00:00")
    mk_review(tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    target = db.get_reviews_by_problem("boj", "1")[0]["id"]

    assert db.update_pending_review("boj", "1", {"efficiency": "good"}, review_id=target)
    assert db.update_pending_review("boj", "1", {"efficiency": "poor"}, review_id=target) is False
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 0, "total": 1}


def test_a_second_problem_adds_to_the_same_tag(at_time):
    at_time("2026-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    at_time("2026-01-02T00:00:00")
    mk_review(problem_id=2, problem_ref="2", tags=["dp"], efficiency="poor")
    assert raw_tag_stats()["dp"] == {"good": 1, "poor": 1, "total": 2}
