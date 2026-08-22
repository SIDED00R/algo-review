"""동시 쓰기에서 이미 과금된 리뷰가 사라지는지 — **Postgres 에서만 재현된다.**

SQLite 는 쓰기를 직렬화하므로 이 계열의 결함이 로컬 스위트에서는 절대 드러나지 않는다.
CI 의 postgres 다리(`.github/workflows/deploy.yml` 의 dialect 매트릭스)가 유일한 재현
환경이라, 이 파일은 그 다리에서만 돈다.

무엇을 지키는가:
- `_bump_tag_stats` 는 없는 태그를 만들 때 `session.get` → `add` → `flush` 를 한다.
  같은 **새 태그**를 담은 두 리뷰가 동시에 저장되면 한쪽이 PK 중복으로 진다. 그 예외가
  `save_review` 를 빠져나가면 트랜잭션이 통째로 롤백되어 **LLM 응답을 이미 받아 과금된
  리뷰 행까지 사라진다**(`routes/review_response.py` 는 분석 후에 저장한다).
- `/api/review-imported` 의 조회 → 리뷰 → 삭제는 원자적이지 않다. 두 요청이 모두 삭제
  전에 조회를 통과하면 둘 다 유료 호출을 하고 리뷰 행을 둘 남긴다.
"""
import threading
import time

import pytest

import db
from conftest import IS_POSTGRES

pytestmark = pytest.mark.skipif(
    not IS_POSTGRES,
    reason="SQLite 는 쓰기를 직렬화해 이 경합이 재현되지 않는다 (CI postgres 다리 전용)")

_THREADS = 4


def _run_concurrently(fn, count=_THREADS):
    """barrier 로 정렬해 동시에 출발시킨다. (결과, 예외) 목록을 돌려준다."""
    barrier = threading.Barrier(count)
    results, errors = [], []

    def worker(i):
        barrier.wait()
        try:
            results.append(fn(i))
        except Exception as e:      # noqa: BLE001 — 무엇이 새는지 보는 것이 목적이다
            errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=30)
    return results, errors


def test_concurrent_first_reviews_sharing_a_new_tag_all_survive():
    """같은 새 태그를 담은 리뷰 4건을 동시에 저장해도 전부 남아야 한다.

    하나라도 예외로 새면 그 사용자는 이미 과금된 리뷰를 잃고 500 을 본다.
    """
    def save(i):
        db.save_review(
            2000 + i, f"문제 {2000 + i}", 5, ["동시성태그"], "print(1)", "fb", "good",
            platform="boj", problem_ref=str(2000 + i), tier_name="Silver I",
            language="Python 3")
        return i

    results, errors = _run_concurrently(save)
    assert not errors, f"동시 저장에서 예외가 샜다 — 과금된 리뷰가 롤백된다: {errors!r}"
    assert len(results) == _THREADS

    stored = {r["problem_ref"] for r in db.get_review_history(50, platform="boj")}
    assert stored >= {str(2000 + i) for i in range(_THREADS)}, "저장되지 않은 리뷰가 있다"


def test_concurrent_first_reviews_keep_tag_stats_consistent():
    """집계는 재계산이 수렴시키므로, 최종 상태가 실제 리뷰 수와 맞아야 한다."""
    def save(i):
        db.save_review(
            3000 + i, f"문제 {3000 + i}", 5, ["수렴태그"], "print(1)", "fb", "poor",
            platform="boj", problem_ref=str(3000 + i), tier_name="Silver I",
            language="Python 3")
        return i

    _, errors = _run_concurrently(save)
    assert not errors, f"동시 저장에서 예외가 샜다: {errors!r}"

    db.reset_tag_stats_rebuild_flag()      # 재계산 쿨다운이 지난 상태를 만든다
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["수렴태그"]["total_count"] == _THREADS, (
        f"재계산 후에도 집계가 맞지 않는다: {stats.get('수렴태그')}")


def test_only_one_request_can_claim_an_imported_record():
    """가져온 기록 하나를 두 요청이 동시에 집으면 한쪽만 진행해야 한다.

    라우터(`routes/solved.py`)는 조회 → 유료 리뷰 → 삭제 순서다. 그 사이가 원자적이지
    않으면 둘 다 조회를 통과해 **각자 LLM 을 돌리고 리뷰 행을 둘 남긴다**(그 문제의 제출
    회차가 1이 아니라 2가 된다). 프론트의 진행 중 가드는 탭 로컬이라 두 탭에서 우회된다.

    여기서는 라우터와 같은 순서를 흉내내되 LLM 자리에 지연만 둔다.
    """
    db.save_solved_problem(4000, "t", 5, ["dp"], code="print(1)", language="Python 3",
                           platform="boj", problem_ref="4000", tier_name="Silver I")

    def claim(_i):
        got = db.get_solved_problem("boj", "4000")
        if not got:
            return False
        time.sleep(0.05)          # LLM 호출 자리 — 이 창에서 다른 요청이 들어온다
        return bool(db.delete_solved_problem("boj", "4000"))

    results, errors = _run_concurrently(claim)
    assert not errors, f"동시 선점에서 예외가 샜다: {errors!r}"
    winners = sum(1 for r in results if r)
    assert winners == 1, (
        f"{winners}개 요청이 같은 기록을 선점했다 — 각자 유료 호출을 하고 리뷰 행을 남긴다")
