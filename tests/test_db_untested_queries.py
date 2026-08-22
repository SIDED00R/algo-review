"""소비처가 하나뿐인 쿼리들의 동작을 직접 고정한다.

아래 함수들은 소비처가 하나뿐이거나 "빈 응답만 단정" 하는 테스트에 가려지기 쉽다 —
무력화해도 다른 테스트가 잡지 못하므로 여기서 각각을 직접 태운다.

| 함수 | 유일한 소비처 | 죽으면 |
|------|--------------|--------|
| `get_tier_history` | `/api/tier-history` → tier-chart.js | 성장 곡선이 영구히 "기록 없음" |
| `get_review_history` | `/api/stats` 의 history + 리포트 프롬프트 입력 | 통계 표가 비고 리포트가 근거 없이 생성됨 |
| `get_solved_problem_keys` | `import_codeforces` 중복 방지 | 매 가져오기가 전량 재삽입을 시도 |
| `get_average_cf_rating` 의 중복 제거 | 추천 난이도 | 같은 문제를 여러 번 푼 만큼 평균이 왜곡 |
"""
import db


def _save(problem_id, ref, platform="boj", **kw):
    args = {
        "problem_id": problem_id, "title": f"문제 {problem_id}", "tier": 10,
        "tags": ["구현"], "code": "print(1)", "feedback": "", "efficiency": "good",
        "platform": platform, "problem_ref": ref, "tier_name": "Silver I",
        "language": "Python 3",
    }
    args.update(kw)
    db.save_review(**args)


# ── get_tier_history ──

def test_tier_history_returns_boj_rows_in_ascending_order(at_time):
    at_time("2026-01-01T10:00:00")
    _save(1000, "1000")
    at_time("2026-02-01T10:00:00")
    _save(1001, "1001", tier=12, tier_name="Gold IV")

    rows = db.get_tier_history()

    assert [r["problem_id"] for r in rows] == [1000, 1001]   # 오름차순
    assert rows[0]["tier"] == 10 and rows[1]["tier"] == 12
    assert rows[0]["tier_name"] == "Silver I"


def test_tier_history_gives_one_point_per_problem_at_its_first_date(at_time):
    """문제당 첫 등장 한 점만 준다 — 재제출이 지나간 구간의 곡선을 바꾸면 안 된다.

    dedup 은 서버가 한다. 소비처(tier-chart.js)가 버릴 회차까지 보내면 응답이 회차 수에
    비례해 자란다. 마지막 회차를 남기는 구현은 예전 문제를 다시 풀 때 그 점을 오늘로 옮겨,
    이미 지나간 날짜의 평균 티어를 소급해서 바꾼다.
    """
    at_time("2026-01-01T10:00:00")
    _save(1000, "1000")
    at_time("2026-08-01T10:00:00")
    _save(1000, "1000")

    rows = db.get_tier_history()

    assert len(rows) == 1
    assert rows[0]["created_at"][:7] == "2026-01"


def test_tier_history_excludes_codeforces_and_unrated():
    _save(0, "4A", platform="codeforces", tier=0, tier_name="Codeforces 800")
    _save(9999, "9999", tier=0, tier_name="Unrated")
    _save(1000, "1000")

    rows = db.get_tier_history()

    assert [r["problem_ref"] for r in rows] == ["1000"]


# ── get_review_history ──

def test_review_history_returns_newest_first_and_respects_limit(at_time):
    for i in range(3):
        at_time(f"2026-0{i + 1}-01T10:00:00")
        _save(1000 + i, str(1000 + i))

    rows = db.get_review_history(limit=2)

    assert [r["problem_id"] for r in rows] == [1002, 1001]   # 최신순
    assert rows[0]["tier_name"] == "Silver I"
    assert rows[0]["tags"] == ["구현"]                        # 정규화를 거친 값이다


def test_review_history_filters_by_platform():
    _save(1000, "1000")
    _save(0, "4A", platform="codeforces", tier=0, tier_name="Codeforces 800")

    assert [r["platform"] for r in db.get_review_history(platform="boj")] == ["boj"]
    assert [r["problem_ref"] for r in db.get_review_history(platform="codeforces")] == ["4A"]
    assert len(db.get_review_history()) == 2   # 필터 없으면 둘 다


# ── get_solved_problem_keys ──

def test_solved_problem_keys_covers_both_tables():
    """리뷰 기록과 가져온 기록을 합쳐야 한다 — 한쪽만 보면 이미 리뷰한 문제를 다시 가져온다."""
    _save(1000, "1000")
    db.save_solved_problem(problem_id=2000, title="B", tier=1, tier_name="Bronze V",
                           tags=[], code="x", language="Python 3",
                           platform="boj", problem_ref="2000")

    keys = db.get_solved_problem_keys()

    assert ("boj", "1000") in keys
    assert ("boj", "2000") in keys


def test_solved_problem_keys_are_deduplicated():
    """같은 문제가 두 테이블에 다 있어도 키는 하나다(set)."""
    _save(1000, "1000")
    db.save_solved_problem(problem_id=1000, title="A", tier=1, tier_name="Bronze V",
                           tags=[], code="x", language="Python 3",
                           platform="boj", problem_ref="1000")

    assert len([k for k in db.get_solved_problem_keys() if k == ("boj", "1000")]) == 1


# ── get_average_cf_rating ──

def test_average_cf_rating_uses_only_the_latest_submission_per_problem(at_time):
    """이름이 약속한 `latest` 를 실제로 검증한다.

    서로 다른 문제를 1회씩만 저장하면 row_number() 중복 제거가 no-op 이라 윈도우 함수를
    통째로 지워도 통과한다. 같은 문제를 두 번 저장해 중복 제거를 실제로 태운다.
    """
    at_time("2026-01-01T10:00:00")
    _save(0, "1A", platform="codeforces", tier=0, tier_name="Codeforces 800")
    at_time("2026-02-01T10:00:00")
    _save(0, "1A", platform="codeforces", tier=0, tier_name="Codeforces 2000")
    at_time("2026-03-01T10:00:00")
    _save(0, "2B", platform="codeforces", tier=0, tier_name="Codeforces 1000")

    # 1A 는 최신(2000)만 반영 → (2000 + 1000) / 2
    assert db.get_average_cf_rating() == 1500.0


def test_average_cf_rating_falls_back_when_no_ratings_parse():
    _save(0, "1A", platform="codeforces", tier=0, tier_name="Unrated")

    assert db.get_average_cf_rating() == 1200.0
