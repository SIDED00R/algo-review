"""동시 쓰기 경합 — **Postgres 에서만 재현된다.**

SQLite 는 쓰기를 직렬화하므로 이 계열의 결함이 로컬 스위트에서는 절대 드러나지 않는다.
CI 의 postgres 다리(`.github/workflows/deploy.yml` 의 dialect 매트릭스)가 유일한 재현
환경이라, 이 파일은 그 다리에서만 돈다.
"""
import threading
import time

import pytest

import db
from conftest import IS_POSTGRES
from db.connection import session_scope
from db.models import TagStat
from db.reviews import _bump_tag_stats

pytestmark = pytest.mark.skipif(
    not IS_POSTGRES,
    reason="SQLite 는 쓰기를 직렬화해 이 경합이 재현되지 않는다 (CI postgres 다리 전용)")


def _run_concurrently(fn, count):
    """barrier 로 정렬해 동시에 출발시킨다. (결과, 예외) 목록을 돌려준다."""
    barrier = threading.Barrier(count)
    results, errors = [], []
    lock = threading.Lock()

    def worker(i):
        barrier.wait()
        try:
            value = fn(i)
            with lock:
                results.append(value)
        except Exception as e:      # noqa: BLE001 — 무엇이 새는지 보는 것이 목적이다
            with lock:
                errors.append(e)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(count)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=60)
    return results, errors


def test_bumping_the_same_new_tag_from_two_transactions_does_not_raise():
    """같은 **새 태그**를 두 트랜잭션이 동시에 만들 때 예외가 새면 안 된다.

    `_bump_tag_stats` 는 `session.get` → 없으면 `add` → `flush` 다. 두 트랜잭션이 둘 다
    "없음" 을 본 뒤 flush 하면 뒤엣것이 PK 중복으로 진다. 그 예외가 `save_review` 를
    빠져나가면 트랜잭션이 통째로 롤백되어 **LLM 응답을 이미 받아 과금된 리뷰 행까지
    사라진다**(`routes/review_response.py` 는 분석 후에 저장한다).

    `session.get` 과 `flush` 사이에 barrier 를 두어 그 창을 정확히 겹친다 — 실제
    운영에서는 이 창이 밀리초 단위지만, 창이 존재한다는 사실 자체가 결함이다.
    """
    tag = "동시성_새태그"
    gate = threading.Barrier(2)

    def bump(_i):
        with session_scope(commit=True) as session:
            # `_bump_tag_stats` 의 첫 동작과 같다 — 여기서 둘 다 "없음" 을 본다.
            assert session.get(TagStat, tag) is None
            gate.wait(timeout=30)
            _bump_tag_stats(session, [tag], "good")
        return True

    _, errors = _run_concurrently(bump, 2)
    assert not errors, (
        f"동시 집계에서 예외가 샜다 — 이 예외는 save_review 를 빠져나가 이미 과금된 "
        f"리뷰를 롤백시킨다: {errors!r}")

    with session_scope() as session:
        stat = session.get(TagStat, tag)
    assert stat is not None and stat.total_count == 2, (
        f"두 번 집계돼야 한다: {stat and stat.total_count}")


def test_concurrent_first_reviews_sharing_a_new_tag_all_survive():
    """같은 새 태그를 담은 리뷰를 동시에 저장해도 전부 남아야 한다.

    위 테스트가 좁힌 창을 실제 `save_review` 경로에서 확인한다.
    """
    def save(i):
        db.save_review(
            2000 + i, f"문제 {2000 + i}", 5, ["동시성태그"], "print(1)", "fb", "good",
            platform="boj", problem_ref=str(2000 + i), tier_name="Silver I",
            language="Python 3")
        return i

    results, errors = _run_concurrently(save, 8)
    assert not errors, f"동시 저장에서 예외가 샜다 — 과금된 리뷰가 롤백된다: {errors!r}"
    assert len(results) == 8

    db.reset_tag_stats_rebuild_flag()      # 재계산 쿨다운이 지난 상태를 만든다
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["동시성태그"]["total_count"] == 8, (
        f"재계산 후에도 집계가 맞지 않는다: {stats.get('동시성태그')}")


def test_only_one_request_can_claim_an_imported_record():
    """가져온 기록 하나를 여러 요청이 동시에 집으면 한쪽만 진행해야 한다.

    라우터(`routes/solved.py`)는 조회 → 유료 리뷰 → 삭제 순서다. 그 사이가 원자적이지
    않으면 여러 요청이 전부 조회를 통과해 **각자 LLM 을 돌리고 리뷰 행을 남긴다**(그
    문제의 제출 회차가 1이 아니라 N 이 된다). 프론트의 진행 중 가드는 탭 로컬이라
    두 탭에서 우회된다.

    여기서는 라우터와 같은 순서를 흉내내되 LLM 자리에 지연만 둔다. 세는 것은
    "몇 개의 요청이 유료 호출까지 갔는가" 다.
    """
    db.save_solved_problem(4000, "t", 5, ["dp"], code="print(1)", language="Python 3",
                           platform="boj", problem_ref="4000", tier_name="Silver I")

    def claim(_i):
        got = db.get_solved_problem("boj", "4000")
        if not got:
            return False
        time.sleep(0.15)          # LLM 호출 자리 — 이 창에서 다른 요청이 들어온다
        db.delete_solved_problem("boj", "4000")
        return True

    results, errors = _run_concurrently(claim, 4)
    assert not errors, f"동시 선점에서 예외가 샜다: {errors!r}"
    reviewed = sum(1 for r in results if r)
    assert reviewed == 1, (
        f"{reviewed}개 요청이 유료 리뷰까지 진행했다 — 조회-삭제가 원자적이지 않다")
