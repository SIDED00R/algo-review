"""db.solved 파사드의 현행 동작 고정."""
import db


def mk_solved(**kw):
    args = {
        "problem_id": 1000,
        "title": "풀이 문제",
        "tier": 10,
        "tags": ["dp"],
        "code": "",
        "language": "",
        "platform": "boj",
        "problem_ref": None,
        "tier_name": "",
    }
    args.update(kw)
    db.save_solved_problem(**args)


def test_save_solved_is_idempotent_on_same_key():
    mk_solved(problem_id=1, problem_ref="1", title="첫 제목")
    mk_solved(problem_id=1, problem_ref="1", title="둘째 제목")
    history = db.get_solved_history()["problems"]
    assert len(history) == 1
    # (platform, problem_ref) 충돌 시 무시 — 최초 값이 유지된다.
    assert history[0]["title"] == "첫 제목"


def test_has_code_flag_reflects_stored_code():
    mk_solved(problem_id=1, problem_ref="1", code="print(1)")
    mk_solved(problem_id=2, problem_ref="2", code="")
    by_ref = {r["problem_ref"]: r for r in db.get_solved_history()["problems"]}
    assert by_ref["1"]["has_code"] is True
    assert by_ref["2"]["has_code"] is False


def test_cached_problem_info_prefers_reviews_over_solved():
    db.save_review(problem_id=7, title="리뷰본", tier=15, tags=["graph"],
                   code="x", feedback="f", efficiency="good", problem_ref="7")
    mk_solved(problem_id=7, problem_ref="7", title="풀이본", tier=99)
    info = db.get_cached_problem_info(7)
    # reviews 가 우선(제목·tier 모두 리뷰본 기준).
    assert info["title"] == "리뷰본"
    assert info["tier"] == 15


def test_cached_problem_info_falls_back_to_solved():
    mk_solved(problem_id=8, problem_ref="8", title="풀이본", tier=20)
    info = db.get_cached_problem_info(8)
    assert info["title"] == "풀이본"
    assert info["tier"] == 20


def test_cached_problem_info_none_when_absent():
    assert db.get_cached_problem_info(12345) is None


def test_restore_after_claim_preserves_imported_at_and_order():
    """claim 후 라우터의 _restore() 와 같은 인자로 재저장하면 원래 imported_at 이
    되살아나야 한다 — 그러지 않으면 목록 순서가 뒤집히고 가져온 날짜가 오늘로 보인다."""
    mk_solved(problem_id=1000, problem_ref="1000", imported_at="2026-01-01T00:00:00+00:00")
    mk_solved(problem_id=2000, problem_ref="2000", imported_at="2026-06-01T00:00:00+00:00")

    claimed = db.claim_solved_problem("boj", "1000")
    # _restore() (routes/solved.py) 와 같은 인자로 재저장한다.
    db.save_solved_problem(
        claimed["problem_id"], claimed.get("title", ""), claimed.get("tier", 0),
        claimed.get("tags", []), code=claimed.get("code", ""),
        language=claimed.get("language", ""), platform="boj",
        problem_ref="1000", tier_name=claimed.get("tier_name", ""),
        imported_at=claimed.get("imported_at", ""))

    history = db.get_solved_history()["problems"]
    refs = [p["problem_ref"] for p in history]
    assert refs == ["2000", "1000"], "claim 이전과 순서가 다르다"
    by_ref = {p["problem_ref"]: p for p in history}
    assert by_ref["1000"]["imported_at"] == "2026-01-01T00:00:00+00:00"
