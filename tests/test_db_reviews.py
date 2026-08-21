"""db.reviews 파사드의 현행 동작 고정 — SQLAlchemy 전환 후에도 이 동작이 유지되어야 한다."""
from datetime import datetime, timedelta

import db
import db.models
from db.connection import session_scope


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


def test_average_tier_excludes_codeforces_rows():
    """BOJ 전용 지표다 — 지금은 CF 리뷰의 tier 가 항상 0 이라 `tier > 0` 만으로도
    걸러지지만 그건 우연이다. CF 레이팅을 티어로 매핑하면 BOJ 평균이 오염된다.
    """
    mk_review(problem_id=1, problem_ref="1", tier=10)
    # CF 행에 실제 티어가 붙는 미래를 흉내낸다.
    mk_review(problem_id=0, platform="codeforces", problem_ref="4A", tier=30,
              tier_name="Codeforces 2400")
    assert db.get_average_tier() == 10.0


def test_average_cf_rating_empty_returns_default():
    assert db.get_average_cf_rating() == 1200.0


def test_average_cf_rating_parses_and_averages_latest():
    mk_review(problem_id=1, platform="codeforces", problem_ref="1A",
              tags=["math"], tier_name="Codeforces 1200")
    mk_review(problem_id=2, platform="codeforces", problem_ref="2B",
              tags=["math"], tier_name="Codeforces 1600")
    assert db.get_average_cf_rating() == 1400.0


def test_problems_grouped_counts_and_reports_latest_efficiency(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="good")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="poor")
    grouped = db.get_problems_grouped()
    assert len(grouped) == 1
    row = grouped[0]
    assert row["submission_count"] == 2
    # 최신 회차(poor, 01-02)의 판정만 내려간다 — 프론트(history.js)가 그 하나만 배지로 쓴다.
    assert row["last_efficiency"] == "poor"
    assert "efficiencies" not in row


def test_pending_review_skips_tag_stats():
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    # 판정이 없는 대기 행은 집계하지 않는다 — 통계가 poor 로 왜곡되면 안 된다.
    assert db.get_tag_stats() == []


def test_update_pending_review_fills_row_without_new_submission():
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency=db.PENDING_EFFICIENCY,
              feedback="", language="Python 3")
    assert db.update_pending_review("boj", "1", {
        "efficiency": "good", "complexity": "O(N)", "better_algorithm": None,
        "feedback": "좋은 풀이", "strengths": ["명확함"], "weaknesses": [],
    }) is True

    rows = db.get_reviews_by_problem("boj", "1")
    assert len(rows) == 1  # 행을 새로 쌓지 않아 제출 회차가 늘지 않는다
    assert rows[0]["efficiency"] == "good"
    assert rows[0]["complexity"] == "O(N)"
    assert rows[0]["better_algorithm"] == ""
    assert rows[0]["feedback"] == "좋은 풀이"
    assert rows[0]["strengths"] == ["명확함"]
    assert rows[0]["language"] == "Python 3"

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    # 대기 등록 때 미룬 첫 집계가 이 시점에 수행된다.
    assert stats["dp"]["good_count"] == 1
    assert stats["dp"]["total_count"] == 1


def test_normal_review_after_pending_still_counts_tags(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    at_time("2024-01-02T00:00:00")
    # 대기 등록 후 리뷰 탭에서 '분석 시작'을 다시 돌린 경우 — 대기 행 때문에 첫 집계를 놓치면 안 된다.
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["good_count"] == 1
    assert stats["dp"]["total_count"] == 1


def test_update_pending_review_without_pending_row():
    mk_review(problem_id=1, problem_ref="1", efficiency="good")
    assert db.update_pending_review("boj", "1", {"efficiency": "ok"}) is False


def test_update_pending_review_does_not_recount_reviewed_problem(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    db.update_pending_review("boj", "1", {"efficiency": "poor"})
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    # 이미 리뷰된 문제의 재제출이므로 집계는 첫 리뷰 1건 그대로다.
    assert stats["dp"]["total_count"] == 1
    assert stats["dp"]["poor_count"] == 0


def test_pending_excluded_from_cf_tag_stats():
    mk_review(problem_id=1, platform="codeforces", problem_ref="1A", tags=["math"],
              efficiency=db.PENDING_EFFICIENCY, tier_name="Codeforces 800")
    assert db.get_cf_tag_stats() == []


def test_pending_counts_as_solved_but_not_in_poor_ratio():
    mk_review(problem_id=1, platform="codeforces", problem_ref="1A", tags=["math"],
              efficiency="good", tier_name="Codeforces 800")
    mk_review(problem_id=2, platform="codeforces", problem_ref="2B", tags=["math"],
              efficiency=db.PENDING_EFFICIENCY, tier_name="Codeforces 900")
    data = {d["tag"]: d for d in db.get_tag_weakness_data("codeforces")}
    assert data["math"]["solve_count"] == 2   # 푼 문제 수에는 포함된다
    assert data["math"]["poor_ratio"] == 0.0  # 판정 비율에는 섞이지 않는다


def test_total_review_count_distinct_by_problem_ref():
    mk_review(problem_id=1, problem_ref="1")
    mk_review(problem_id=1, problem_ref="1")  # 재제출 — 중복 문제
    mk_review(problem_id=2, problem_ref="2")
    assert db.get_total_review_count("boj") == 2


def test_problem_statement_roundtrips():
    """붙여 넣은 문제 설명이 그대로 돌아와야 한다 — 불러오기가 이 값으로 폼을 복원한다."""
    body = "첫 줄에 N 이 주어진다.\n1 <= N <= 100"
    mk_review(problem_id=1, problem_ref="1", problem_statement=body)
    rows = db.get_reviews_by_problem("boj", "1")
    assert rows[0]["problem_statement"] == body


def test_problem_statement_defaults_to_empty():
    """저장 시 넘기지 않으면 빈 문자열이다 — 불러오기는 이 값을 조건 없이 대입해
    이전 문제의 본문이 폼에 남지 않게 한다(resolve_statement 가 붙여 넣은 본문을 우선한다)."""
    mk_review(problem_id=2, problem_ref="2")
    rows = db.get_reviews_by_problem("boj", "2")
    assert rows[0]["problem_statement"] == ""


# ── LLM 이 null 을 준 필드 ──
#
# `.get(key, default)` 는 **키가 있고 값이 None** 이면 default 를 적용하지 않는다.
# reviews.complexity·feedback 은 NOT NULL 이라 그 None 이 그대로 흘러가면 저장이
# IntegrityError 로 죽고, 이미 과금된 LLM 응답과 tag_stats 첫 집계가 롤백으로 함께 사라진다.
# 저장 경로가 둘이라(save_review / update_pending_review) 한쪽만 막으면 다른 쪽에서 터진다.

_NULL_RESULT = {
    "efficiency": "ok", "complexity": None, "better_algorithm": None,
    "feedback": None, "strengths": None, "weaknesses": None,
}


def test_update_pending_review_survives_null_string_fields():
    db.save_review(problem_id=1000, title="A+B", tier=1, tags=["math"],
                   code="print(1)", feedback="", efficiency=db.PENDING_EFFICIENCY,
                   problem_ref="1000", language="Python 3")

    db.update_pending_review("boj", "1000", _NULL_RESULT)

    row = db.get_reviews_by_problem("boj", "1000")[0]
    assert row["complexity"] == ""
    assert row["feedback"] == ""
    assert row["better_algorithm"] == ""
    assert row["efficiency"] == "ok"
    assert len(db.get_reviews_by_problem("boj", "1000")) == 1   # 회차가 늘지 않는다


def test_save_review_survives_null_string_fields():
    db.save_review(problem_id=2000, title="B", tier=1, tags=["math"],
                   code="x", efficiency="good", problem_ref="2000", language="Python 3",
                   complexity=None, better_algorithm=None, feedback=None)

    row = db.get_reviews_by_problem("boj", "2000")[0]
    assert row["complexity"] == ""
    assert row["feedback"] == ""


def test_analyzer_normalizes_null_string_fields():
    """생산자에서 끝낸다 — 소비처마다 막으면 한쪽이 빠진다(실제로 그랬다)."""
    import analyzer

    result = {"efficiency": "good", "complexity": None, "feedback": None,
              "better_algorithm": None}
    normalized = analyzer.normalize_review_result(result)

    assert normalized["complexity"] == ""
    assert normalized["feedback"] == ""
    assert normalized["better_algorithm"] == ""


def test_tag_stats_rebuilds_the_table_when_it_is_empty():
    """tag_stats 는 BOJ 첫 제출에서만 채워지는 비정규화 테이블이라, 그 경로를 타지 않고
    들어온 행(마이그레이션·백필·직접 INSERT)만 있으면 비어 있다. 복원이 없으면 BOJ 리뷰가
    아무리 많아도 /api/report 가 "아직 저장된 기록이 없습니다"(400)를 낸다."""
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    mk_review(problem_id=2, problem_ref="2", tags=["dp"], efficiency="poor")
    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["total_count"] == 2
    assert stats["dp"]["good_count"] == 1 and stats["dp"]["poor_count"] == 1

    # 읽기마다 계산하는 폴백이 아니라 **테이블을 복원**해야 한다.
    with session_scope() as session:
        assert session.query(db.models.TagStat).count() == 1


def test_a_new_review_after_rebuild_does_not_collapse_the_numbers(at_time):
    """복원 뒤 새 리뷰가 들어와도 숫자가 이어져야 한다.

    읽을 때마다 폴백을 계산하는 방식은 스위치가 all-or-nothing 이다 — 빈 tag_stats +
    BOJ 리뷰 다수 상태에서 새 리뷰 1건이 들어오면 그 1건짜리 TagStat 행 때문에 폴백을
    건너뛰어 통계가 붕괴한다.
    """
    at_time("2024-01-01T00:00:00")
    for i in range(5):
        mk_review(problem_id=i, problem_ref=str(i), tags=["dp"], efficiency="good")
    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()

    before = {s["tag"]: s["total_count"] for s in db.get_tag_stats()}
    assert before["dp"] == 5

    at_time("2024-02-01T00:00:00")
    mk_review(problem_id=99, problem_ref="99", tags=["dp"], efficiency="poor")

    after = {s["tag"]: s["total_count"] for s in db.get_tag_stats()}
    assert after["dp"] == 6, f"복원 후 새 리뷰 1건에 통계가 {before['dp']} → {after['dp']} 로 튀었다"


def test_rebuild_counts_first_submissions_only():
    """복원 기준이 _bump_tag_stats 와 달라지면 두 경로가 뒤집힐 때 숫자가 튄다."""
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="poor")   # 재제출
    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["total_count"] == 1, "재제출까지 세면 _bump_tag_stats 와 어긋난다"
    assert stats["dp"]["good_count"] == 1


def test_tag_stats_fallback_ignores_codeforces_and_pending_rows():
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    mk_review(problem_id=0, platform="codeforces", problem_ref="4A",
              tags=["dp"], efficiency="poor", tier_name="Codeforces 800")
    mk_review(problem_id=3, problem_ref="3", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["dp"]["total_count"] == 1, "CF 행이나 대기 행이 BOJ 집계에 섞였다"
