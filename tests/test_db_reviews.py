"""db.reviews 파사드의 현행 동작 고정 — SQLAlchemy 전환 후에도 이 동작이 유지되어야 한다."""
from datetime import datetime, timedelta

import db
import db.models
from db.connection import session_scope


def _latest_id(problem_ref, platform="boj"):
    """호출부(routes/rereview.py)가 집는 회차 — 목록의 첫 행이 최신이다."""
    return db.get_reviews_by_problem(platform, problem_ref)[0]["id"]


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
    assert grouped["total"] == 1
    assert len(grouped["problems"]) == 1
    row = grouped["problems"][0]
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
    }, review_id=_latest_id("1")) is True

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
    assert db.update_pending_review("boj", "1", {"efficiency": "ok"},
                                    review_id=_latest_id("1")) is False


def test_update_pending_review_does_not_recount_reviewed_problem(at_time):
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    db.update_pending_review("boj", "1", {"efficiency": "poor"}, review_id=_latest_id("1"))
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

    db.update_pending_review("boj", "1000", _NULL_RESULT, review_id=_latest_id("1000"))

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
    """생산자에서 끝낸다 — 소비처마다 막으면 한쪽이 빠진다."""
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


def test_rebuild_matches_the_incremental_basis_when_the_first_row_is_pending(at_time):
    """복원 기준은 `_bump_tag_stats` 와 같아야 한다 — **첫 non-pending 행**.

    대기 등록 후 리뷰 탭에서 다시 리뷰하면 행이 [pending, good] 이 된다. 복원이
    "created_at 최소 행" 을 첫 제출로 보면 그 행이 pending 이라 문제 전체가 집계에서
    빠지고, 표가 non-empty 가 되는 순간 다시 복원되지 않아 영구 고착된다.
    """
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["math"], efficiency="good")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=2, problem_ref="2", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    at_time("2024-01-03T00:00:00")
    mk_review(problem_id=2, problem_ref="2", tags=["dp"], efficiency="poor")

    incremental = {s["tag"]: (s["total_count"], s["good_count"], s["poor_count"])
                   for s in db.get_tag_stats()}

    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()
    db.reset_tag_stats_rebuild_flag()   # 재계산 쿨다운이 지난 상태를 만든다
    restored = {s["tag"]: (s["total_count"], s["good_count"], s["poor_count"])
                for s in db.get_tag_stats()}

    assert restored == incremental, f"증분 {incremental} vs 복원 {restored}"


def test_rebuild_handles_two_pending_rows_for_one_problem(at_time):
    """같은 문제를 두 번 대기 등록하면 오래된 대기 행이 남는다 — 그 행이 첫 행이어도
    집계는 첫 non-pending 행을 따라야 한다."""
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=5, problem_ref="5", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=5, problem_ref="5", tags=["dp"], efficiency=db.PENDING_EFFICIENCY)
    assert db.update_pending_review("boj", "5", {"efficiency": "good", "complexity": "",
                                                 "better_algorithm": "", "feedback": "",
                                                 "strengths": [], "weaknesses": []},
                                    review_id=_latest_id("5"))

    incremental = {s["tag"]: s["total_count"] for s in db.get_tag_stats()}
    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()
    db.reset_tag_stats_rebuild_flag()   # 재계산 쿨다운이 지난 상태를 만든다
    restored = {s["tag"]: s["total_count"] for s in db.get_tag_stats()}

    assert restored == incremental, f"증분 {incremental} vs 복원 {restored}"


def test_codeforces_weakness_does_not_borrow_boj_verdicts(at_time):
    """CF 취약 태그의 poor 비율은 CF 행만 센다.

    tag_stats 는 BOJ 전용이라 CF 는 항상 폴백 경로를 탄다. 그 폴백이 BOJ 를 세면, 태그
    이름이 겹치는 순간(solved.ac 가 ko 표시명을 주지 않는 `math`·`dp`·`greedy` 등) BOJ 의
    판정이 CF 추천 점수로 새어 든다 — recommender._score_tags 가 가중치 0.3 으로 쓴다.
    """
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["math"], efficiency="poor")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=0, problem_ref="4A", platform="codeforces", tags=["math"],
              efficiency="good", tier=0, tier_name="Codeforces 800")
    at_time("2024-01-03T00:00:00")
    mk_review(problem_id=0, problem_ref="5A", platform="codeforces", tags=["math"],
              efficiency="good", tier=0, tier_name="Codeforces 800")

    cf = {row["tag"]: row for row in db.get_tag_weakness_data("codeforces")}
    assert cf["math"]["poor_ratio"] == 0.0, "BOJ 의 poor 판정이 CF 취약 점수로 샜다"

    boj = {row["tag"]: row for row in db.get_tag_weakness_data("boj")}
    assert boj["math"]["poor_ratio"] == 1.0


def test_codeforces_weakness_matches_the_codeforces_stats_page(at_time):
    """CF 폴백은 /api/stats 가 보여주는 것과 **같은 모집단**(전 회차)을 센다.

    모집단이 갈리면 같은 데이터로 통계 화면과 추천의 poor 비율이 달라진다.
    """
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=0, problem_ref="4A", platform="codeforces", tags=["dp"],
              efficiency="poor", tier=0, tier_name="Codeforces 800")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=0, problem_ref="4A", platform="codeforces", tags=["dp"],
              efficiency="good", tier=0, tier_name="Codeforces 800")

    stats = {s["tag"]: s for s in db.get_cf_tag_stats()}
    weakness = {row["tag"]: row for row in db.get_tag_weakness_data("codeforces")}
    expected = stats["dp"]["poor_count"] / stats["dp"]["total_count"]
    assert weakness["dp"]["poor_ratio"] == expected


def test_backfilled_reviews_are_reconciled_into_tag_stats(at_time):
    """증분 경로를 타지 않고 들어온 행(백필·마이그레이션)도 재계산이 흡수한다.

    "비어 있을 때만 복원" 방식은 이 상황을 벗어나지 못한다 — 백필 후 새 리뷰 1건이
    들어오면 표가 그 1건짜리로 굳고, 표가 비어 있지 않으므로 다시 복원되지 않는다.
    """
    at_time("2024-01-01T00:00:00")
    db.get_tag_stats()                       # 빈 DB 에서 한 번 조회 — 표는 계속 비어 있다
    for i in range(3):                       # 증분 갱신을 타지 않는 경로를 흉내낸다
        with session_scope(commit=True) as session:
            session.add(db.models.Review(
                platform="boj", problem_ref=str(2000 + i), problem_id=2000 + i,
                title="t", tier=1, tier_name="Bronze V", tags='["math"]',
                language="Python 3", code="x", feedback="", efficiency="poor",
                complexity="", strengths="[]", weaknesses="[]",
                created_at=f"2024-01-0{i + 2}T00:00:00"))

    db.reset_tag_stats_rebuild_flag()        # 재계산 쿨다운이 지난 상태
    assert {s["tag"]: s["total_count"] for s in db.get_tag_stats()} == {"math": 3}

    at_time("2024-02-01T00:00:00")
    mk_review(problem_id=3000, problem_ref="3000", tags=["math"], efficiency="good")
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["math"]["total_count"] == 4, "백필분이 새 리뷰 1건에 밀려 사라졌다"
    assert stats["math"]["poor_count"] == 3


def test_reconcile_drops_tags_that_no_longer_exist(at_time):
    """reviews 에서 사라진 태그의 잔재를 표에 남기지 않는다."""
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tags=["dp"], efficiency="good")
    assert "dp" in {s["tag"] for s in db.get_tag_stats()}

    with session_scope(commit=True) as session:
        session.query(db.models.Review).delete()
    db.reset_tag_stats_rebuild_flag()
    assert db.get_tag_stats() == []


def test_boj_weakness_matches_the_boj_stats_page_without_a_reconcile(at_time):
    """추천의 poor 비율이 통계 화면과 같아야 한다 — **재계산을 트리거하지 않고도**.

    tag_stats 의 재계산은 `get_tag_stats()` 만 트리거하고 그것은 /api/stats·/api/report
    에서만 불린다. 추천만 쓰는 프로세스가 표를 읽으면, 증분 경로를 타지 않고 들어온
    행(백필)이 반영되지 않은 값을 인스턴스 수명 내내 쓴다.
    """
    at_time("2024-01-01T00:00:00")
    for i in range(10):                      # 증분 경로를 타지 않는 백필
        with session_scope(commit=True) as session:
            session.add(db.models.Review(
                platform="boj", problem_ref=str(4000 + i), problem_id=4000 + i,
                title="t", tier=1, tier_name="Bronze V", tags='["math"]',
                language="Python 3", code="x", feedback="", efficiency="poor",
                complexity="", strengths="[]", weaknesses="[]",
                created_at=f"2024-01-{i + 1:02d}T00:00:00"))
    at_time("2024-02-01T00:00:00")
    mk_review(problem_id=5000, problem_ref="5000", tags=["math"], efficiency="good")

    # get_tag_stats() 를 부르기 **전에** 읽는다 — 추천만 쓰는 프로세스와 같은 상태다.
    weakness = {row["tag"]: row["poor_ratio"] for row in db.get_tag_weakness_data("boj")}

    stats = {s["tag"]: s for s in db.get_tag_stats()}
    expected = stats["math"]["poor_count"] / stats["math"]["total_count"]
    assert weakness["math"] == expected, (
        f"추천 {weakness['math']} vs 통계 화면 {expected} — 재계산 없이 표를 읽었다")


def test_weakness_counts_pending_rows_the_same_way_the_stats_table_does(at_time):
    """대기 행은 판정이 없어 poor 비율 모집단에서 빠진다 — 두 경로가 같아야 한다."""
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=6000, problem_ref="6000", tags=["dp"],
              efficiency=db.PENDING_EFFICIENCY)
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=6000, problem_ref="6000", tags=["dp"], efficiency="poor")
    at_time("2024-01-03T00:00:00")
    mk_review(problem_id=6001, problem_ref="6001", tags=["dp"], efficiency="good")

    weakness = {row["tag"]: row["poor_ratio"] for row in db.get_tag_weakness_data("boj")}
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert weakness["dp"] == stats["dp"]["poor_count"] / stats["dp"]["total_count"]
    assert stats["dp"]["total_count"] == 2, "대기 행이 모집단에 섞였다"


def test_weakness_does_not_read_the_denormalised_table(at_time):
    """표를 통째로 지워도 추천의 poor 비율은 그대로여야 한다.

    이 단정이 "tag_stats 를 읽지 않는다" 는 계약을 고정한다 — 읽는다면 표를 지운 순간
    값이 달라진다.
    """
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=7000, problem_ref="7000", tags=["greedy"], efficiency="poor")
    before = {row["tag"]: row["poor_ratio"] for row in db.get_tag_weakness_data("boj")}

    with session_scope(commit=True) as session:
        session.query(db.models.TagStat).delete()
    after = {row["tag"]: row["poor_ratio"] for row in db.get_tag_weakness_data("boj")}
    assert after == before == {"greedy": 1.0}


def test_solve_count_counts_problems_not_submissions(at_time):
    """solve_count 는 회차가 아니라 **문제 수**다.

    전 회차를 세면 같은 문제를 여러 번 고쳐 올린 태그일수록 수가 부풀고,
    recommender._score_tags 의 count_score(가중치 0.5)에서 "덜 취약" 으로 평가된다 —
    가장 많이 고쳐 쓴, 즉 가장 어려워한 태그가 추천에서 밀리는 방향이다.
    """
    at_time("2024-01-01T00:00:00")
    for i in range(5):                        # 같은 문제를 5회 재제출
        at_time(f"2024-01-0{i + 1}T00:00:00")
        mk_review(problem_id=8000, problem_ref="8000", tags=["dp"], efficiency="poor")
    at_time("2024-02-01T00:00:00")
    mk_review(problem_id=8001, problem_ref="8001", tags=["greedy"], efficiency="poor")

    weakness = {row["tag"]: row["solve_count"] for row in db.get_tag_weakness_data("boj")}
    assert weakness == {"dp": 1, "greedy": 1}, "재제출이 문제 수를 부풀렸다"


def test_solve_count_merges_reviews_and_imported_history(at_time):
    """리뷰 기록과 가져온 기록에 같은 문제가 있어도 한 번만 센다."""
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=9000, problem_ref="9000", tags=["dp"], efficiency="poor")
    db.save_solved_problem(9000, "t", 1, ["dp"], code="x", language="Python 3",
                           platform="boj", problem_ref="9000", tier_name="Bronze V")
    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=9001, problem_ref="9001", tags=["dp"], efficiency="good")

    weakness = {row["tag"]: row["solve_count"] for row in db.get_tag_weakness_data("boj")}
    assert weakness["dp"] == 2, "같은 문제가 두 표에 있어 두 번 세어졌다"


def test_average_tier_is_not_shown_without_graded_rows(at_time):
    """get_average_tier 의 10.0 은 추천 난이도 기본값이지 표시값이 아니다."""
    assert not db.has_graded_tier()
    at_time("2024-01-01T00:00:00")
    mk_review(problem_id=9100, problem_ref="9100", tags=["dp"], tier=0, efficiency="poor")
    assert not db.has_graded_tier(), "티어 0 행이 등급으로 세어졌다"

    at_time("2024-01-02T00:00:00")
    mk_review(problem_id=9101, problem_ref="9101", tags=["dp"], tier=5, efficiency="poor")
    assert db.has_graded_tier()
