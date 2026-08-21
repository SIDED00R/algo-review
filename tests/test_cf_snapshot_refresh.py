"""CF problemset 스냅샷의 강제 갱신 (회귀).

problemset 전체는 수 MB · timeout 30s 다. 예전 구현은 `lru_cache.cache_clear()` 로
**먼저 버리고 나중에 받았다** — 재다운로드가 실패하면 정상 스냅샷까지 잃고, 그 뒤 CF 기능
전부(추천·테마·리뷰)가 요청마다 전체 다운로드를 재시도한다. 오타 한 번 + CF 일시 장애가
겹치면 프로세스 단위로 열화된다.

lru_cache 는 사용자 함수 실행 중 락을 잡지 않아 **동시 miss 를 합치지도 못한다** —
"다른 요청까지 재다운로드를 유발한다, 쿨다운으로 막는다" 는 주석이 실제로는 거짓이었다.
"""
import threading

import pytest

from clients import codeforces


def _problem(contest_id, index, rating=800):
    return {"contestId": contest_id, "index": index, "name": f"{contest_id}{index}",
            "rating": rating, "tags": ["math"]}


@pytest.fixture(autouse=True)
def clean_snapshot(monkeypatch):
    """모듈 전역 스냅샷은 프로세스 수명이라 테스트마다 비운다."""
    monkeypatch.setattr(codeforces, "_snapshot", None)
    monkeypatch.setattr(codeforces, "_lookup", None)
    monkeypatch.setattr(codeforces, "_last_force_refresh", 0.0)
    yield


def test_failed_refresh_keeps_the_working_snapshot(monkeypatch):
    calls = {"n": 0}

    def _fetch():
        calls["n"] += 1
        if calls["n"] == 1:
            return ([_problem(4, "A")], {})
        raise ValueError("Codeforces problemset 응답이 비어 있습니다.")

    monkeypatch.setattr(codeforces, "_fetch_cf_problemset", _fetch)

    assert codeforces.get_codeforces_problem_info("4A")["problem_ref"] == "4A"

    # 없는 문제를 조회하면 강제 갱신을 시도하고 **실패**한다.
    with pytest.raises(ValueError, match="찾을 수 없습니다"):
        codeforces.get_codeforces_problem_info("9999Z")

    # 기존 스냅샷이 살아 있어야 한다 — 예전에는 여기서 재다운로드가 시작됐다.
    before = calls["n"]
    assert codeforces.get_codeforces_problem_info("4A")["problem_ref"] == "4A"
    assert calls["n"] == before, "정상 스냅샷을 버려 다시 내려받았다"


def test_successful_refresh_installs_the_new_snapshot(monkeypatch):
    calls = {"n": 0}

    def _fetch():
        calls["n"] += 1
        return ([_problem(4, "A")], {}) if calls["n"] == 1 else ([_problem(4, "A"), _problem(1900, "B")], {})

    monkeypatch.setattr(codeforces, "_fetch_cf_problemset", _fetch)
    codeforces.get_codeforces_problem_info("4A")

    # 새 대회 문제는 첫 스냅샷에 없다 — 갱신 후 재조회로 찾아야 한다.
    assert codeforces.get_codeforces_problem_info("1900B")["problem_ref"] == "1900B"
    assert calls["n"] == 2


def test_cooldown_blocks_a_second_refresh(monkeypatch):
    calls = {"n": 0}

    def _fetch():
        calls["n"] += 1
        return ([_problem(4, "A")], {})

    monkeypatch.setattr(codeforces, "_fetch_cf_problemset", _fetch)
    codeforces.get_codeforces_problem_info("4A")

    for _ in range(3):
        with pytest.raises(ValueError, match="찾을 수 없습니다"):
            codeforces.get_codeforces_problem_info("9999Z")

    # 첫 다운로드 1 + 강제 갱신 1 — 쿨다운이 나머지 두 번을 막는다.
    assert calls["n"] == 2


def test_concurrent_misses_download_only_once(monkeypatch):
    """lru_cache 는 동시 호출을 합치지 못한다 — 스레드풀에서 각자 수 MB 를 내려받았다."""
    calls = {"n": 0}
    started = threading.Barrier(4)

    def _fetch():
        calls["n"] += 1
        # 다운로드가 느린 상황을 흉내낸다.
        threading.Event().wait(0.05)
        return ([_problem(4, "A")], {})

    monkeypatch.setattr(codeforces, "_fetch_cf_problemset", _fetch)

    def _worker():
        started.wait()
        codeforces._get_cf_problemset_snapshot()

    threads = [threading.Thread(target=_worker) for _ in range(4)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert calls["n"] == 1, f"동시 miss 4건이 {calls['n']}회 내려받았다"
