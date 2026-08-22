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

    라우터는 `claim_solved_problem`(단일 DELETE ... RETURNING)으로 선점한다. 세는 것은
    "몇 개의 요청이 유료 호출까지 갔는가" 다.
    """
    db.save_solved_problem(4000, "t", 5, ["dp"], code="print(1)", language="Python 3",
                           platform="boj", problem_ref="4000", tier_name="Silver I")

    def claim(_i):
        got = db.claim_solved_problem("boj", "4000")
        if not got:
            return False
        time.sleep(0.15)          # LLM 호출 자리 — 이 창에서 다른 요청이 들어온다
        return True

    results, errors = _run_concurrently(claim, 4)
    assert not errors, f"동시 선점에서 예외가 샜다: {errors!r}"
    reviewed = sum(1 for r in results if r)
    assert reviewed == 1, (
        f"{reviewed}개 요청이 유료 리뷰까지 진행했다 — 조회-삭제가 원자적이지 않다")


def test_only_one_request_fills_a_pending_round():
    """같은 대기 회차를 동시에 채우면 **한 요청만** 성공해야 한다.

    조회와 쓰기를 나누면 둘 다 "대기 상태" 를 보고 차례로 덮어써, 뒤늦게 도착한 리뷰가
    앞선 것을 지운다(둘 다 이미 과금된 LLM 결과다). UPDATE 의 WHERE 에
    `efficiency = PENDING` 을 함께 걸어 선점으로 만든다.
    """
    db.save_review(problem_id=1, title="문제", tier=10, tags=["dp"], code="print(1)",
                   feedback="", efficiency=db.PENDING_EFFICIENCY, problem_ref="1",
                   language="Python 3")
    target = db.get_reviews_by_problem("boj", "1")[0]["id"]

    def fill(i):
        return db.update_pending_review("boj", "1", {
            "efficiency": "good" if i == 0 else "poor",
            "complexity": "", "better_algorithm": "",
            "feedback": f"{i} 번 요청의 리뷰", "strengths": [], "weaknesses": [],
        }, review_id=target)

    results, errors = _run_concurrently(fill, 8)
    assert not errors, errors
    assert sum(1 for r in results if r) == 1, \
        f"선점이 성립하지 않았다 — {sum(1 for r in results if r)} 개 요청이 성공했다"

    row = db.get_reviews_by_problem("boj", "1")[0]
    assert row["efficiency"] != db.PENDING_EFFICIENCY
    assert row["feedback"].endswith("번 요청의 리뷰")


def test_concurrent_fills_of_two_rounds_reconcile_to_one_count():
    """같은 문제의 대기 회차 둘을 동시에 채웠을 때, 집계가 결국 1 로 수렴해야 한다.

    증분 집계()는 이 창에서 정확하지 않을 수 있다 — 둘 다 "아직 리뷰된
    회차가 없다" 를 보고 각자 세거나(2), 한쪽이 상대의 미커밋 INSERT 를 못 봐 건너뛴다(1).
    어느 쪽이 되는지는 타이밍에 달렸으므로 여기서 못박지 않는다.

    못박는 것은 **수렴**이다. 60초 주기 전면 재계산이 reviews 를 다시 세어 정답으로
    맞추므로, 그 경로를 태운 값은 타이밍과 무관하게 1 이어야 한다.
    """
    for _ in range(2):
        db.save_review(problem_id=2, title="문제", tier=10, tags=["greedy"], code="print(2)",
                       feedback="", efficiency=db.PENDING_EFFICIENCY, problem_ref="2",
                       language="Python 3")
        time.sleep(0.01)   # created_at 이 겹치지 않게 — 회차 순서가 결정되어야 한다
    ids = [r["id"] for r in db.get_reviews_by_problem("boj", "2")]
    assert len(ids) == 2

    def fill(i):
        return db.update_pending_review("boj", "2", {
            "efficiency": "good", "complexity": "", "better_algorithm": "",
            "feedback": "", "strengths": [], "weaknesses": [],
        }, review_id=ids[i])

    results, errors = _run_concurrently(fill, 2)
    assert not errors, errors
    assert all(results), "서로 다른 회차이므로 둘 다 성공해야 한다"

    db.reset_tag_stats_rebuild_flag()
    stats = {s["tag"]: s for s in db.get_tag_stats()}
    assert stats["greedy"]["total_count"] == 1
