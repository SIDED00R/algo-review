"""저장되는 시각의 계약 — 항상 UTC, 항상 오프셋.

오프셋 없이 저장하면 그 문자열이 어느 지역의 벽시계인지 알 수 없다. Cloud Run 은 UTC,
개발 기계는 KST 라 같은 코드가 만든 값의 의미가 환경마다 달랐고, 그래서 같은 제출이
GitHub README(KST 로 변환)와 앱 화면(원문을 그대로 자름)에서 **다른 날짜**로 보였다.
한국 시각 00:00~09:00 제출은 앱에서 전날로 찍혔다 — 하루의 9시간.
"""
from datetime import datetime, timedelta, timezone

import db
import pytest
from routes.helpers import _submitted_at_str
from timestamps import parse_stored, utc_now_iso

KST = timezone(timedelta(hours=9))

# 한국 사용자가 2026-08-22 08:00 KST 에 제출한 순간. UTC 컨테이너의 벽시계는 전날 23:00 이다.
EARLY_MORNING_KST = "2026-08-21T23:00:00"


def mk_review(**kw):
    args = {
        "problem_id": 1000, "title": "새벽에 푼 문제", "tier": 10, "tags": ["dp"],
        "code": "print(1)", "feedback": "f", "efficiency": "good",
        "platform": "boj", "problem_ref": "1000", "tier_name": "",
    }
    args.update(kw)
    db.save_review(**args)


def test_saved_timestamps_carry_an_offset():
    """오프셋이 없으면 그 값이 가리키는 순간이 하나로 정해지지 않는다."""
    mk_review()
    db.save_solved_problem(problem_id=2000, title="가져온 문제", tier=10, tags=["dp"],
                           problem_ref="2000", code="x")

    created = db.get_reviews_by_problem("boj", "1000")[0]["created_at"]
    imported = db.get_solved_history()["problems"][0]["imported_at"]
    for label, value in (("created_at", created), ("imported_at", imported)):
        assert datetime.fromisoformat(value).tzinfo is not None, f"{label} 에 오프셋이 없다"


def test_the_app_and_the_github_readme_agree_on_the_day(at_time):
    """같은 제출이 두 날짜로 보이면 안 된다.

    README 는 KST 로 변환해 적고, 화면은 보는 사람의 시간대로 적는다. 한국 사용자라면
    둘이 같은 날이어야 한다. 저장값을 그냥 잘라 쓰던 시절에는 여기서 하루가 어긋났다.
    """
    at_time(EARLY_MORNING_KST)
    mk_review()

    created = db.get_reviews_by_problem("boj", "1000")[0]["created_at"]
    readme_day = _submitted_at_str(created)
    screen_day = parse_stored(created).astimezone(KST).strftime("%Y-%m-%d")

    assert readme_day.startswith("2026년 8월 22일"), readme_day
    assert screen_day == "2026-08-22"
    # 잘라 쓰면 전날이 된다 — 고친 것이 무엇인지 못박는다.
    assert created[:10] == "2026-08-21"


def test_grouped_and_chart_timestamps_are_parseable_too(at_time):
    """목록·성장 곡선도 같은 값을 쓴다 — 한 곳만 고치면 화면마다 날짜가 갈린다."""
    at_time(EARLY_MORNING_KST)
    mk_review()

    last_submitted = db.get_problems_grouped()["problems"][0]["last_submitted"]
    chart_at = db.get_tier_history()[0]["created_at"]
    for label, value in (("last_submitted", last_submitted), ("tier_history", chart_at)):
        assert parse_stored(value).astimezone(KST).strftime("%Y-%m-%d") == "2026-08-22", label


# ── parse_stored 의 규칙 ────────────────────────────────────────────────

def test_parse_stored_reads_a_bare_timestamp_as_utc():
    """오프셋 없이 저장된 옛 행은 전부 Cloud Run(UTC)이 쓴 것이다."""
    assert parse_stored("2026-08-21T23:00:00") == datetime(2026, 8, 21, 23, tzinfo=timezone.utc)


def test_parse_stored_keeps_an_explicit_offset():
    assert parse_stored("2026-08-22T08:00:00+09:00").astimezone(timezone.utc) \
        == datetime(2026, 8, 21, 23, tzinfo=timezone.utc)


def test_utc_now_iso_is_aware_and_sorts_lexicographically():
    """created_at 은 SQL 정렬 키다 — 사전순이 시간순과 어긋나면 '최신 회차' 가 뒤집힌다."""
    first = utc_now_iso()
    second = utc_now_iso()
    assert parse_stored(first).tzinfo is not None
    assert first <= second


# ── 추천 점수의 최신성 ──────────────────────────────────────────────────

def test_recency_survives_the_offset_format(monkeypatch):
    """days_since 계산이 형식 변화에 삼켜지면 최신성 점수가 통째로 평탄해진다.

    naive 로 빼면 aware 값에서 TypeError 가 나고, 그것을 except 가 삼켜 모든 태그가
    365 가 된다 — 점수는 계속 나오는데 최신성 항이 죽는다(조용한 오답).
    """
    import recommender
    recent = (datetime.now(timezone.utc) - timedelta(days=2)).isoformat()
    old = (datetime.now(timezone.utc) - timedelta(days=200)).isoformat()
    data = [
        {"tag": "recent", "solve_count": 1, "poor_ratio": 0.0, "last_solved_at": recent},
        {"tag": "old", "solve_count": 1, "poor_ratio": 0.0, "last_solved_at": old},
    ]
    scored = {d["tag"]: d for d in recommender._score_tags(data)}
    assert scored["recent"]["days_since"] == 2
    assert scored["old"]["days_since"] == 200


def test_recency_does_not_flip_sign_on_a_future_timestamp():
    """미래 시각이 섞이면 max_days 가 0 이하가 되어 recency 점수의 부호가 뒤집힌다."""
    import recommender
    future = (datetime.now(timezone.utc) + timedelta(days=3)).isoformat()
    data = [{"tag": "t", "solve_count": 1, "poor_ratio": 0.0, "last_solved_at": future}]
    scored = recommender._score_tags(data)
    assert scored[0]["weakness_score"] >= 0


@pytest.mark.parametrize("bad", ["", "not-a-date", None])
def test_recency_falls_back_when_the_value_is_unusable(bad):
    import recommender
    data = [{"tag": "t", "solve_count": 1, "poor_ratio": 0.0, "last_solved_at": bad}]
    assert recommender._score_tags(data)[0]["days_since"] == 365
