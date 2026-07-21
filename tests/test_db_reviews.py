"""db.reviews 파사드의 현행 동작 고정 — SQLAlchemy 전환 후에도 이 동작이 유지되어야 한다."""
from datetime import datetime, timedelta

import db


def mk_review(**kw):
    args = {
        "problem_id": 1000,
        "title": "테스트 문제",
        "tier": 10,
        "tags": ["dp", "greedy"],
        "code": "print(1)",
        "feedback": "좋음",
        "efficiency": "good",
        "platform": "boj",
        "problem_ref": None,
        "tier_name": "",
    }
    args.update(kw)
    db.save_review(**args)


def test_tag_stats_increment_on_first_boj_submission():
    mk_review(problem_id=1, tags=["dp"], efficiency="good")
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["good_count"] == 1
    assert stats["dp"]["total_count"] == 1
    assert stats["dp"]["poor_count"] == 0


def test_tag_stats_not_incremented_on_resubmission():
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="poor")
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    # 같은 문제 재제출은 tag_stats 를 건드리지 않는다(첫 제출만 집계).
    assert stats["dp"]["total_count"] == 1
    assert stats["dp"]["good_count"] == 1


def test_tag_stats_untouched_for_codeforces():
    mk_review(problem_id=5, platform="codeforces", problem_ref="1A",
              tags=["math"], tier_name="Codeforces 800")
    assert db.get_tag_stats() == []


def test_average_tier_empty_returns_default():
    assert db.get_average_tier() == 10.0


def test_average_tier_uses_latest_submission_per_problem(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tier=10)
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tier=30)
    # 같은 문제의 최신 제출(tier=30)만 평균에 반영된다.
    assert db.get_average_tier() == 30.0


def test_average_tier_window_limited_to_30(at_time):
    # 가장 오래된 항목에 튀는 tier 를 두고, 최신 30개(tier=10)만 잡히는지 확인.
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=999, problem_ref="999", tier=5000)
    base = datetime(2024, 2, 1)
    for i in range(30):
        at_time((base + timedelta(days=i)).isoformat())
        mk_review(problem_id=i, problem_ref=str(i), tier=10)
    assert db.get_average_tier() == 10.0


def test_average_cf_rating_empty_returns_default():
    assert db.get_average_cf_rating() == 1200.0


def test_average_cf_rating_parses_and_averages_latest():
    mk_review(problem_id=1, platform="codeforces", problem_ref="1A",
              tags=["math"], tier_name="Codeforces 1200")
    mk_review(problem_id=2, platform="codeforces", problem_ref="2B",
              tags=["math"], tier_name="Codeforces 1600")
    assert db.get_average_cf_rating() == 1400.0


def test_problems_grouped_counts_and_orders_efficiencies(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="good")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="poor")
    grouped = db.get_problems_grouped()
    assert len(grouped) == 1
    row = grouped[0]
    assert row["submission_count"] == 2
    # 최신 제출이 먼저 — poor(01-02) → good(01-01)
    assert row["efficiencies"] == "poor,good"


def test_total_review_count_distinct_by_problem_ref():
    mk_review(problem_id=1, problem_ref="1")
    mk_review(problem_id=1, problem_ref="1")  # 재제출 — 중복 문제
    mk_review(problem_id=2, problem_ref="2")
    assert db.get_total_review_count("boj") == 2
