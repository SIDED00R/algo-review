"""목록 API 의 페이지네이션·필터 계약.

리뷰 기록과 가져온 기록은 서버가 걸러 페이지 단위로 준다. 전 행을 보내던 시절에는
화면이 20건만 그리는데도 응답이 기록 수에 비례해 자랐다(실측: 리뷰 1만 행 →
444ms·1.41MB·피크 10.1MB). 여기서 고정하는 것은 그 구조가 되돌아가지 않는다는 것이다.
"""
import db
from db.paging import MAX_PAGE_SIZE


def mk_review(**kw):
    args = {
        "problem_id": 1000, "title": "테스트 문제", "tier": 10, "tags": ["dp"],
        "code": "print(1)", "feedback": "좋음", "efficiency": "good",
        "platform": "boj", "problem_ref": None, "tier_name": "",
    }
    args.update(kw)
    db.save_review(**args)


def mk_solved(**kw):
    args = {
        "problem_id": 2000, "title": "가져온 문제", "tier": 10, "tags": ["bfs"],
        "code": "print(1)", "language": "Python 3", "platform": "boj",
        "problem_ref": None, "tier_name": "",
    }
    args.update(kw)
    db.save_solved_problem(**args)


def seed_reviews(n, start=1000):
    for i in range(n):
        pid = start + i
        mk_review(problem_id=pid, problem_ref=str(pid), title=f"문제 {i}")


# ── 상한과 경계 ──────────────────────────────────────────────────────────

def test_per_page_is_capped_by_the_server():
    """상한이 없으면 `?per_page=999999` 하나로 전 행 응답이 되살아난다."""
    seed_reviews(MAX_PAGE_SIZE + 5)
    page = db.get_problems_grouped(per_page=999999)
    assert len(page["problems"]) == MAX_PAGE_SIZE
    assert page["total"] == MAX_PAGE_SIZE + 5


def test_solved_per_page_is_capped_too():
    """두 목록이 같은 규약을 쓴다 — 한쪽에만 상한이 빠지면 그쪽이 구멍이다."""
    for i in range(MAX_PAGE_SIZE + 3):
        mk_solved(problem_id=2000 + i, problem_ref=str(2000 + i))
    page = db.get_solved_history(per_page=999999)
    assert len(page["problems"]) == MAX_PAGE_SIZE
    assert page["total"] == MAX_PAGE_SIZE + 3


def test_out_of_range_paging_arguments_are_clamped():
    seed_reviews(3)
    assert len(db.get_problems_grouped(page=0)["problems"]) == 3
    assert len(db.get_problems_grouped(per_page=0)["problems"]) == 3
    # 범위를 넘은 페이지는 빈 목록이되 total 은 그대로다(페이저가 되돌아갈 수 있어야 한다).
    beyond = db.get_problems_grouped(page=99, per_page=2)
    assert beyond["problems"] == [] and beyond["total"] == 3


# ── 페이지가 전체를 빠짐없이 한 번씩 덮는지 ──────────────────────────────

def test_pages_partition_the_whole_set_without_gaps_or_overlaps():
    """정렬이 불안정하면 같은 문제가 두 페이지에 나오고 다른 문제는 사라진다."""
    seed_reviews(25)
    seen = []
    for page in (1, 2, 3):
        seen += [p["problem_ref"] for p in
                 db.get_problems_grouped(page=page, per_page=10)["problems"]]
    assert len(seen) == 25
    assert len(set(seen)) == 25


def test_total_does_not_change_with_the_page():
    seed_reviews(25)
    assert {db.get_problems_grouped(page=p, per_page=10)["total"] for p in (1, 2, 3)} == {25}


# ── 필터가 SQL 에서 걸리는지 ─────────────────────────────────────────────

def test_search_matches_title_ref_and_tags():
    mk_review(problem_id=1, problem_ref="1", title="다익스트라 연습", tags=["graph"])
    mk_review(problem_id=2, problem_ref="2", title="다른 문제", tags=["dp"])

    def refs(**kw):
        return {p["problem_ref"] for p in db.get_problems_grouped(**kw)["problems"]}

    assert refs(q="다익스트라") == {"1"}
    assert refs(q="graph") == {"1"}
    assert refs(q="2") == {"2"}
    assert refs(q="없는말") == set()


def test_search_ignores_case_and_surrounding_space():
    mk_review(problem_id=1, problem_ref="1", title="Dijkstra")
    assert db.get_problems_grouped(q="  dIjKsTrA ")["total"] == 1


def test_tier_and_platform_and_efficiency_filters():
    mk_review(problem_id=1, problem_ref="1", tier=5, efficiency="good")
    mk_review(problem_id=2, problem_ref="2", tier=15, efficiency="poor")
    mk_review(problem_id=0, problem_ref="4A", platform="codeforces", tier=0)

    assert db.get_problems_grouped(tier_min=11, tier_max=20)["total"] == 1
    assert db.get_problems_grouped(platform="codeforces")["total"] == 1
    assert db.get_problems_grouped(eff="poor")["total"] == 1


def test_efficiency_filter_looks_at_the_latest_round_only(at_time):
    """배지가 최신 회차를 보여주므로 필터도 같은 회차를 봐야 한다.

    어느 회차든 맞으면 통과시키면, `poor` 로 걸러 놓고 `효율적` 배지가 달린 행이 나온다.
    """
    at_time("2026-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="poor")
    at_time("2026-02-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="good")

    assert db.get_problems_grouped(eff="good")["total"] == 1
    assert db.get_problems_grouped(eff="poor")["total"] == 0


def test_filtered_total_counts_the_filtered_rows(at_time):
    """필터가 있을 때의 total 은 싼 DISTINCT 로 셀 수 없다.

    필터 없는 경로는 `DISTINCT platform:ref` 로 센다(50배 빠르다). 필터는 **최신 회차의
    값**에 걸리므로 같은 방식으로 세면 걸러진 문제까지 수에 들어가고, 페이저가 있지도 않은
    페이지를 그린다.

    3번 문제가 그 함정이다 — `good` 회차를 가졌지만 최신은 `poor` 라 목록에서 빠진다.
    """
    at_time("2026-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="poor")
    mk_review(problem_id=3, problem_ref="3", efficiency="good")
    at_time("2026-02-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", efficiency="good")
    mk_review(problem_id=2, problem_ref="2", efficiency="good")
    mk_review(problem_id=3, problem_ref="3", efficiency="poor")

    page = db.get_problems_grouped(eff="good")
    assert {p["problem_ref"] for p in page["problems"]} == {"1", "2"}
    # DISTINCT 로 세면 3번까지 들어가 3 이 된다.
    assert page["total"] == 2


# ── 정렬 ────────────────────────────────────────────────────────────────

def test_problem_number_sort_is_numeric_not_lexicographic():
    """문자열로 정렬하면 `1000` 이 `999` 보다 앞선다 — 번호순이 아니게 된다."""
    for pid in (999, 1000, 1001):
        mk_review(problem_id=pid, problem_ref=str(pid))
    refs = [p["problem_ref"] for p in
            db.get_problems_grouped(sort="pid_asc")["problems"]]
    assert refs == ["999", "1000", "1001"]


def test_solved_number_sort_is_numeric_in_both_directions():
    for pid in (999, 1000, 1001):
        mk_solved(problem_id=pid, problem_ref=str(pid))
    asc = [p["problem_ref"] for p in db.get_solved_history(sort="id-asc")["problems"]]
    desc = [p["problem_ref"] for p in db.get_solved_history(sort="id-desc")["problems"]]
    assert asc == ["999", "1000", "1001"]
    assert desc == ["1001", "1000", "999"]


def test_tier_sort_orders_by_tier(at_time):
    at_time("2026-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1", tier=5)
    at_time("2026-01-02T00:00:00")
    mk_review(problem_id=2, problem_ref="2", tier=20)
    tiers = [p["tier"] for p in db.get_problems_grouped(sort="tier_desc")["problems"]]
    assert tiers == [20, 5]
    tiers = [p["tier"] for p in db.get_problems_grouped(sort="tier_asc")["problems"]]
    assert tiers == [5, 20]


def test_default_sort_is_most_recently_submitted_first(at_time):
    at_time("2026-01-01T00:00:00")
    mk_review(problem_id=1, problem_ref="1")
    at_time("2026-02-01T00:00:00")
    mk_review(problem_id=2, problem_ref="2")
    refs = [p["problem_ref"] for p in db.get_problems_grouped()["problems"]]
    assert refs == ["2", "1"]


# ── 목록에 싣지 않는 것 ──────────────────────────────────────────────────

def test_list_rows_never_carry_the_code():
    """코드가 목록에 섞이면 한 페이지 응답이 수십 배로 뛴다 — 상세에서만 준다."""
    mk_review(problem_id=1, problem_ref="1", code="x" * 5000)
    mk_solved(problem_id=2, problem_ref="2", code="y" * 5000)
    assert "code" not in db.get_problems_grouped()["problems"][0]
    solved = db.get_solved_history()["problems"][0]
    assert "code" not in solved
    assert solved["has_code"] is True
