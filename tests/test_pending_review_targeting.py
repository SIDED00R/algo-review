"""'리뷰 대기' 채우기는 **리뷰한 그 회차**에 써야 한다.

재리뷰는 LLM 호출에 10~20초가 걸린다. 그 사이에 같은 문제로 대기 회차가 하나 더 쌓이면
(메인 탭의 '리뷰 없이 올리기'), "가장 최신 대기 행" 을 찾아 쓰는 구현은 **방금 리뷰한 코드가
아닌 다른 코드**의 회차에 결과를 붙인다. 화면에는 코드 B 와 코드 A 의 리뷰가 나란히 놓이고,
그 상태로 GitHub README 까지 올라간다. 실패도 오류도 없이 조용히 틀린다.
"""
import db
import pytest


def mk_pending(code, at_time, when, **kw):
    at_time(when)
    args = {
        "problem_id": 1000, "title": "문제", "tier": 10, "tags": ["dp"],
        "code": code, "feedback": "", "efficiency": db.PENDING_EFFICIENCY,
        "platform": "boj", "problem_ref": "1000", "tier_name": "", "language": "Python 3",
    }
    args.update(kw)
    db.save_review(**args)


RESULT_FOR_A = {
    "efficiency": "poor", "complexity": "O(n^2)", "better_algorithm": "정렬 후 투 포인터",
    "feedback": "코드 A 에 대한 리뷰", "strengths": ["A 의 장점"], "weaknesses": ["A 의 단점"],
}


def test_review_lands_on_the_round_that_was_reviewed(at_time):
    """리뷰 중에 대기 회차가 하나 더 생겨도 결과는 리뷰한 회차에 붙어야 한다."""
    mk_pending("코드 A", at_time, "2026-01-01T00:00:00")
    reviewed = db.get_reviews_by_problem("boj", "1000")[0]      # 재리뷰가 집어 든 회차
    assert reviewed["code"] == "코드 A"

    # --- LLM 이 도는 10~20초 사이에 사용자가 같은 문제를 다시 올린다 ---
    mk_pending("코드 B", at_time, "2026-01-02T00:00:00")

    assert db.update_pending_review("boj", "1000", RESULT_FOR_A, review_id=reviewed["id"])

    rounds = {r["code"]: r for r in db.get_reviews_by_problem("boj", "1000")}
    assert rounds["코드 A"]["feedback"] == "코드 A 에 대한 리뷰"
    assert rounds["코드 A"]["efficiency"] == "poor"
    # 코드 B 는 아직 리뷰되지 않았다 — 남의 리뷰를 받으면 안 된다.
    assert rounds["코드 B"]["efficiency"] == db.PENDING_EFFICIENCY
    assert rounds["코드 B"]["feedback"] == ""


def test_filling_an_already_filled_round_is_refused(at_time):
    """동시에 두 요청이 같은 회차를 채우면 뒤늦은 쪽이 앞선 결과를 덮어쓰면 안 된다."""
    mk_pending("코드 A", at_time, "2026-01-01T00:00:00")
    target = db.get_reviews_by_problem("boj", "1000")[0]

    assert db.update_pending_review("boj", "1000", RESULT_FOR_A, review_id=target["id"])
    second = dict(RESULT_FOR_A, feedback="뒤늦게 도착한 두 번째 리뷰", efficiency="good")
    assert db.update_pending_review("boj", "1000", second, review_id=target["id"]) is False

    row = db.get_reviews_by_problem("boj", "1000")[0]
    assert row["feedback"] == "코드 A 에 대한 리뷰"
    assert row["efficiency"] == "poor"


def test_a_vanished_round_is_reported_not_silently_redirected(at_time):
    """대상 회차가 사라졌으면 다른 회차로 흘려보내지 않고 실패로 알린다."""
    mk_pending("코드 A", at_time, "2026-01-01T00:00:00")
    mk_pending("코드 B", at_time, "2026-01-02T00:00:00")
    assert db.update_pending_review("boj", "1000", RESULT_FOR_A, review_id=999999) is False
    for r in db.get_reviews_by_problem("boj", "1000"):
        assert r["efficiency"] == db.PENDING_EFFICIENCY


def test_tag_stats_count_once_even_when_two_pending_rounds_exist(at_time):
    """집계는 문제의 첫 리뷰에서 한 번만 — 대기 회차가 둘이어도 두 번 세지 않는다."""
    mk_pending("코드 A", at_time, "2026-01-01T00:00:00", tags=["dp"])
    first = db.get_reviews_by_problem("boj", "1000")[0]
    mk_pending("코드 B", at_time, "2026-01-02T00:00:00", tags=["dp"])
    second = db.get_reviews_by_problem("boj", "1000")[0]

    db.update_pending_review("boj", "1000", RESULT_FOR_A, review_id=first["id"])
    db.update_pending_review("boj", "1000", dict(RESULT_FOR_A, efficiency="good"),
                             review_id=second["id"])

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["total_count"] == 1


def test_review_id_is_required(at_time):
    """대상을 지정하지 않는 호출은 막는다 — '가장 최신 대기 행' 추측이 이 버그의 원인이었다."""
    mk_pending("코드 A", at_time, "2026-01-01T00:00:00")
    with pytest.raises(TypeError):
        db.update_pending_review("boj", "1000", RESULT_FOR_A)
