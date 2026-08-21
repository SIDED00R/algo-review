"""db.cache 파사드의 현행 동작 고정."""
import db


def test_cache_set_overwrites_same_key():
    db.cache_set("k", {"v": 1})
    db.cache_set("k", {"v": 2})
    assert db.cache_get_stale("k") == {"v": 2}


def test_cache_get_returns_fresh_payload():
    db.cache_set("k", {"v": 1})
    assert db.cache_get("k", max_age_sec=3600) == {"v": 1}


def test_cache_get_expired_returns_none():
    db.cache_set("k", {"v": 1})
    # max_age_sec=0 이면 방금 쓴 값도 만료로 판정된다.
    assert db.cache_get("k", max_age_sec=0) is None


def test_cache_get_missing_returns_none():
    assert db.cache_get("nope", max_age_sec=3600) is None


def test_cache_get_stale_ignores_age():
    db.cache_set("k", {"v": 1})
    assert db.cache_get_stale("k") == {"v": 1}


def test_cache_get_stale_missing_returns_none():
    assert db.cache_get_stale("nope") is None


# ── 자가 복구 (회귀) ──
#
# cache_get 의 두 try/except 는 주석에서 "여기서 예외가 나가면 호출부가 cache_set 에
# 도달하지 못해 그 키가 영구히 자가 복구 불능이 된다" 고 위험도를 명시한다. 그런데
# 정상 경로만 테스트가 있어, 두 가드를 제거해도 스위트가 초록이었다.

def _write_raw(key, payload, updated_at):
    """정상 경로로는 만들 수 없는 손상 행을 직접 넣는다(수동 편집·부분 쓰기 재현)."""
    from sqlalchemy import text

    from db.connection import session_scope
    with session_scope(commit=True) as session:
        session.execute(
            text("INSERT INTO api_cache (cache_key, payload, updated_at) "
                 "VALUES (:k, :p, :u)"),
            {"k": key, "p": payload, "u": updated_at},
        )


def test_unparsable_timestamp_is_treated_as_expired_not_raised():
    _write_raw("broken-time", '{"a": 1}', "not-a-date")

    assert db.cache_get("broken-time", 3600) is None


def test_corrupt_payload_is_treated_as_missing_not_raised():
    from datetime import datetime, timezone
    _write_raw("broken-json", "{not json", datetime.now(timezone.utc).isoformat())

    assert db.cache_get("broken-json", 3600) is None
    assert db.cache_get_stale("broken-json") is None


def test_a_broken_row_can_be_repaired_by_the_next_write():
    """가드의 존재 이유 — 예외가 나가면 호출부가 cache_set 에 도달하지 못한다."""
    _write_raw("repairable", "{not json", "not-a-date")

    assert db.cache_get("repairable", 3600) is None   # 예외가 아니라 None
    db.cache_set("repairable", {"ok": True})          # 호출부가 여기까지 온다
    assert db.cache_get("repairable", 3600) == {"ok": True}
