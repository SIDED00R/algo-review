"""solved.ac 태그 이름 → 검색 키 변환의 캐시 규약.

키를 틀리면 검색이 200 + 빈 목록을 주므로 `ProblemSearchError` 도 나지 않는다 —
`/api/recommend` 가 error 없이 그 태그만 조용히 빈다. 그래서 **추측 키가 만료 없는
성공 캐시에 들어가면** 프로세스 수명 동안 그 태그의 추천이 죽는다.
"""
from unittest.mock import MagicMock, patch

import pytest

from clients import solved_ac


@pytest.fixture(autouse=True)
def clean_caches():
    solved_ac._TAG_KEY_CACHE.clear()
    solved_ac._TAG_KEY_FALLBACK.clear()
    yield
    solved_ac._TAG_KEY_CACHE.clear()
    solved_ac._TAG_KEY_FALLBACK.clear()


def _response(items):
    resp = MagicMock()
    resp.raise_for_status.return_value = None
    resp.json.return_value = {"items": items}
    return resp


def _patch_list(items):
    return patch.object(solved_ac.requests, "get", lambda *a, **k: _response(items))


def test_a_null_key_does_not_stop_the_rest_of_the_list():
    """`"key": null` 항목이 섞여도 그 뒤 항목이 캐시에 들어간다.

    `.get("key","")` 는 명시적 null 에 None 을 돌려주고, 이어지는 `.lower()` 가
    AttributeError 를 낸다. 그 예외를 except 가 삼키면 목록 순회가 중간에 끊겨,
    응답 안에 있던 태그도 추측 키로 나간다.
    """
    items = [
        {"key": "dp", "displayNames": [{"name": "다이나믹 프로그래밍"}]},
        {"key": None, "displayNames": [{"name": "깨진 항목"}]},
        {"key": "greedy", "displayNames": [{"name": "그리디 알고리즘"}]},
    ]
    with _patch_list(items):
        assert solved_ac.get_tag_key_by_name("그리디 알고리즘") == "greedy"
    assert None not in solved_ac._TAG_KEY_CACHE.values()
    assert "" not in solved_ac._TAG_KEY_CACHE


def test_a_guessed_key_never_enters_the_permanent_cache():
    """목록에 없는 태그의 추측 키는 성공 캐시에 들어가지 않는다."""
    with _patch_list([{"key": "dp", "displayNames": []}]):
        assert solved_ac.get_tag_key_by_name("소수 판별") == "소수_판별"
    assert "소수 판별" not in solved_ac._TAG_KEY_CACHE
    assert "소수 판별" in solved_ac._TAG_KEY_FALLBACK


def test_a_guessed_key_expires_and_yields_to_the_real_one():
    """목록이 갱신되면 만료 후 진짜 키를 받아온다 — 추측이 영구 고착되지 않는다."""
    with _patch_list([{"key": "dp", "displayNames": []}]):
        assert solved_ac.get_tag_key_by_name("소수 판별") == "소수_판별"

    real = [{"key": "primality_test", "displayNames": [{"name": "소수 판별"}]}]
    with _patch_list(real):
        assert solved_ac.get_tag_key_by_name("소수 판별") == "소수_판별", "만료 전에는 재조회하지 않는다"
        guess, _ = solved_ac._TAG_KEY_FALLBACK["소수 판별"]
        solved_ac._TAG_KEY_FALLBACK["소수 판별"] = (guess, 0.0)     # 만료시킨다
        assert solved_ac.get_tag_key_by_name("소수 판별") == "primality_test"


def test_absent_tags_get_a_longer_reprieve_than_unreachable_ones():
    """조회 실패(일시 장애)와 목록에 없음(안정적 사실)은 만료가 다르다.

    같은 TTL 을 쓰면 목록에 없는 태그가 60초마다 전체 태그 목록을 다시 내려받는다.
    """
    assert solved_ac._FALLBACK_TTL_ABSENT > solved_ac._FALLBACK_TTL_UNREACHABLE

    with _patch_list([{"key": "dp", "displayNames": []}]):
        solved_ac.get_tag_key_by_name("없는 태그")
    absent_expiry = solved_ac._TAG_KEY_FALLBACK["없는 태그"][1]

    with patch.object(solved_ac.requests, "get", side_effect=RuntimeError("down")):
        solved_ac.get_tag_key_by_name("다른 태그")
    unreachable_expiry = solved_ac._TAG_KEY_FALLBACK["다른 태그"][1]

    assert absent_expiry > unreachable_expiry


def test_a_lookup_failure_does_not_poison_the_permanent_cache():
    with patch.object(solved_ac.requests, "get", side_effect=RuntimeError("blocked")):
        assert solved_ac.get_tag_key_by_name("이분 탐색") == "이분_탐색"
    assert solved_ac._TAG_KEY_CACHE == {}
