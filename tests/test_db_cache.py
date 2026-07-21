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
