import json
import logging
import threading
import time

from sqlalchemy import distinct, func, select, update
from sqlalchemy.exc import DBAPIError, IntegrityError

from db.connection import session_scope
from db.models import Review, SolvedHistory, TagStat
from db.normalize import normalize_common_row
from db.paging import DEFAULT_PAGE_SIZE, paging_bounds, search_filter
from timestamps import utc_now_iso

logger = logging.getLogger("uvicorn.error")


PENDING_EFFICIENCY = "pending"
"""LLM 리뷰 없이 등록한 행의 효율성 마커.

good/ok/poor 판정이 없는 상태이므로 태그 통계 집계에서 제외한다 —
update_pending_review 가 실제 리뷰로 채울 때 집계한다.
"""


def _normalize_review_row(row: dict) -> dict:
    """리뷰 상세 행 — JSON 리스트 컬럼을 파싱한다.

    **strengths/weaknesses 를 select 한 행에만 쓴다.** 목록 응답(grouped·history)은 그
    컬럼을 뽑지 않는데 여기를 통과시키면 빈 리스트 두 개가 응답에 주입된다 — 프론트는
    쓰지 않지만 "이 API 는 강점/약점을 준다" 는 잘못된 계약이 응답에 박힌다.
    """
    normalize_common_row(row)

    for key in ("strengths", "weaknesses"):
        value = row.get(key)
        # 저장 경로가 막혀 있어도 옛 행에는 문자열 "null" 이 남아 있을 수 있다.
        row[key] = json.loads(value or "[]") if isinstance(value, str) else (value or [])
    return row


def _bump_tag_stats(session, tags: list, efficiency: str) -> None:
    """태그별 good/poor 카운트를 누적한다. BOJ 첫 리뷰에서만 호출한다.

    없는 태그는 **savepoint 안에서** 만든다. `get` → 없으면 `add` → `flush` 는 두 트랜잭션이
    둘 다 "없음" 을 본 창에서 뒤엣것이 PK 중복으로 진다(CI postgres 다리에서 재현). 그
    IntegrityError 가 `save_review` 를 빠져나가면 트랜잭션이 통째로 롤백되어 **LLM 응답을
    이미 받아 과금된 리뷰 행까지 사라진다** — 라우터는 분석 후에 저장한다.

    savepoint 로 감싸면 충돌한 INSERT 만 되돌리고 바깥 트랜잭션은 살아 있다. 되돌린 뒤
    상대가 넣은 행을 다시 읽어 그 위에 누적한다.
    """
    for tag in tags:
        stat = session.get(TagStat, tag)
        if stat is None:
            try:
                with session.begin_nested():
                    stat = TagStat(tag=tag, good_count=0, poor_count=0, total_count=0)
                    session.add(stat)
                    session.flush()
            except IntegrityError:
                # 다른 트랜잭션이 먼저 만들었다 — 그 행을 읽어 이어서 센다.
                session.expunge_all()
                stat = session.get(TagStat, tag)
                if stat is None:
                    # 커밋되지 않은 상대의 INSERT 였다면 여기서도 안 보인다.
                    # 이 회차의 집계는 건너뛴다 — 60초 주기 전면 재계산이 정답으로 맞춘다.
                    logger.info("tag_stats 동시 생성 경합 — 재계산이 맞춘다 (tag=%s)", tag)
                    continue
        stat.total_count += 1
        if efficiency == "good":
            stat.good_count += 1
        else:
            stat.poor_count += 1


def save_review(problem_id: int, title: str, tier: int, tags: list,
                code: str, feedback: str, efficiency: str,
                complexity: str = "", better_algorithm: str = "",
                strengths: list = None, weaknesses: list = None,
                platform: str = "boj", problem_ref: str | None = None,
                tier_name: str = "", language: str = "", problem_statement: str = ""):
    tags = tags or []
    strengths = strengths or []
    weaknesses = weaknesses or []
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()

    with session_scope(commit=True) as session:
        # 대기 행은 아직 집계되지 않았으므로 첫 제출 판정에서 뺀다 —
        # update_pending_review 의 reviewed_before 기준과 어긋나면 집계가 영구 누락된다.
        prior = session.scalar(
            select(func.count()).select_from(Review)
            .where(Review.platform == platform, Review.problem_ref == problem_ref,
                   Review.efficiency != PENDING_EFFICIENCY))
        is_first_submission = (prior == 0)

        session.add(Review(
            problem_id=problem_id, platform=platform, problem_ref=problem_ref,
            title=title, tier=tier, tier_name=tier_name,
            # NOT NULL 컬럼에는 `or ""` 를 쓴다 — 호출부가 None 을 넘기면(LLM 이 null 을 준
            # 필드가 그대로 흘러오는 경우) IntegrityError 로 죽고, 이미 과금된 응답이
            # 롤백으로 사라진다. analyzer.normalize_review_result 가 먼저 막지만 이 함수는
            # dict 를 직접 받는 공개 경로다.
            tags=json.dumps(tags, ensure_ascii=False), code=code, feedback=feedback or "",
            efficiency=efficiency, complexity=complexity or "",
            better_algorithm=better_algorithm or "",
            strengths=json.dumps(strengths, ensure_ascii=False),
            weaknesses=json.dumps(weaknesses, ensure_ascii=False),
            language=language or "", problem_statement=problem_statement or "",
            created_at=utc_now_iso(),
        ))

        # tag_stats 는 BOJ 첫 제출에서만 집계한다. 리뷰 대기 행은 판정이 없어 제외한다.
        if is_first_submission and platform == "boj" and efficiency != PENDING_EFFICIENCY:
            _bump_tag_stats(session, tags, efficiency)


def update_pending_review(platform: str, problem_ref: str, result: dict,
                          *, review_id: int) -> bool:
    """`review_id` 회차를 실제 리뷰 결과로 채운다. 그 행이 대기 상태가 아니면 False.

    **대상을 호출부가 지정한다.** "가장 최신 대기 행" 을 여기서 찾으면, LLM 이 도는
    10~20초 사이에 같은 문제로 대기 회차가 하나 더 쌓였을 때 **리뷰한 적 없는 코드**에
    결과가 붙는다(그 상태로 GitHub README 까지 올라간다). 실패도 오류도 없이 조용히 틀린다.

    `efficiency == PENDING` 조건을 UPDATE 에 함께 건다 — 조회와 쓰기 사이가 벌어지면
    동시 요청 둘이 같은 행을 차례로 덮어써 뒤늦게 도착한 결과가 앞선 것을 지운다.
    이긴 쪽만 True 를 받는다.

    행을 새로 쌓지 않으므로 제출 회차가 늘지 않는다. save_review 가 미룬 tag_stats 집계는
    이 문제의 첫 리뷰인 경우 여기서 수행한다.
    """
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or "").strip()

    efficiency = result["efficiency"]
    with session_scope(commit=True) as session:
        # UPDATE 보다 먼저 센다 — 뒤로 옮기면 방금 채운 자기 행이 포함되어 집계가 누락된다.
        reviewed_before = session.scalar(
            select(func.count()).select_from(Review)
            .where(Review.platform == platform, Review.problem_ref == problem_ref,
                   Review.efficiency != PENDING_EFFICIENCY))

        claimed = session.execute(
            update(Review)
            .where(Review.id == review_id,
                   Review.platform == platform, Review.problem_ref == problem_ref,
                   )
            .values(
                efficiency=efficiency,
                # `or ""` 로 통일한다 — `.get(key, default)` 는 LLM 이 값에 null 을 준 경우
                # default 를 적용하지 않아 NOT NULL 컬럼에 None 이 들어간다(analyzer 가 이미
                # 정규화하지만, 이 함수는 dict 를 직접 받는 공개 경로라 여기서도 막는다).
                complexity=result.get("complexity") or "",
                better_algorithm=result.get("better_algorithm") or "",
                feedback=result.get("feedback") or "",
                # 리스트도 `or []` 로 통일한다 — json.dumps(None) 은 IntegrityError 없이
                # 문자열 "null" 을 만들어 통과하고, 읽을 때 None 이 되어 API 가 null 을 내보낸다.
                strengths=json.dumps(result.get("strengths") or [], ensure_ascii=False),
                weaknesses=json.dumps(result.get("weaknesses") or [], ensure_ascii=False),
            )
        ).rowcount
        if not claimed:
            return False

        if platform == "boj" and reviewed_before == 0:
            tags = session.scalar(select(Review.tags).where(Review.id == review_id))
            _bump_tag_stats(session, json.loads(tags), efficiency)
        return True


def get_stored_problem_statement(platform: str, problem_ref: str) -> str:
    """그 문제의 회차 중 **비어 있지 않은 가장 최근 본문**.

    `problem_statement` 는 회차(reviews 행)마다 저장되지만 의미는 **문제**의 속성이다.
    최신 행만 보면, 1회차에 붙여 넣은 본문이 본문 없이 저장된 2회차에 가려진다 — BOJ 는
    acmicpc.net 종료로 스크래핑이 상시 실패하므로 앱이 이미 가진 본문을 두고 사용자에게
    다시 붙여넣으라고 요구하게 되고, 재리뷰는 빈 문제 설명으로 유료 호출을 낸다.
    """
    platform = (platform or "boj").strip().lower()
    with session_scope() as session:
        return session.scalar(
            select(Review.problem_statement)
            .where(Review.platform == platform, Review.problem_ref == str(problem_ref).strip(),
                   Review.problem_statement != "")
            .order_by(Review.created_at.desc()).limit(1)) or ""


def refresh_unresolved_problem_metadata(problem_id: int, info: dict) -> int:
    """자리표시 메타로 저장된 BOJ 행들을 실제 문제 메타로 갱신하고, 갱신한 행 수를 돌려준다.

    solved.ac 일시 장애 중 저장된 행은 제목이 "문제 {번호}", 티어 0, 태그 없음이다.
    제목·티어·태그는 제출이 아니라 **문제**의 속성이라 갱신이 맞다 — 제출 코드·판정·
    피드백은 건드리지 않는다.

    집계 기준(`_first_judged_rows`)이 문제당 첫 판정 행이므로, 이 갱신이 없으면 새 리뷰를
    아무리 해도 그 문제의 태그가 통계·추천에 영영 들어오지 않는다.
    """
    placeholder = f"문제 {problem_id}"
    tags_json = json.dumps(info.get("tags") or [], ensure_ascii=False)
    with session_scope(commit=True) as session:
        return session.execute(
            update(Review)
            .where(Review.platform == "boj", Review.problem_id == problem_id,
                   Review.title == placeholder, Review.tier == 0)
            .values(title=info["title"], tier=info["tier"],
                    tier_name=info.get("tier_name") or "", tags=tags_json)
        ).rowcount

def _first_judged_rows(rows: list) -> list:
    """문제당 **첫 판정 행**만 남긴다. 입력은 created_at 오름차순이어야 한다.

    기준은 `_bump_tag_stats` 호출부와 같다 — **첫 non-pending 행**이다. 대기 행은
    판정이 없어 집계 대상이 아니므로 dedup 대상에서도 뺀다. 대기 행을 포함해
    "created_at 최소 행" 을 첫 제출로 보면, 대기 등록 후 리뷰한 문제는 첫 행이 pending
    이라 문제 전체가 집계에서 빠진다.
    """
    seen = set()
    firsts = []
    for row in rows:
        if row.get("efficiency") == PENDING_EFFICIENCY:
            continue
        if row["problem_ref"] in seen:
            continue
        seen.add(row["problem_ref"])
        firsts.append(row)
    return firsts


def _first_submission_tag_counts(session, platform: str) -> dict:
    """한 플랫폼의 리뷰에서 문제당 첫 판정 행만 세어 태그별 good/poor 를 만든다.

    platform 은 호출부가 반드시 넘긴다 — 기본값을 두면 다른 플랫폼의 집계에 BOJ 행이
    섞여도 호출부에서 드러나지 않는다.
    """
    rows = session.execute(
        select(Review.problem_ref, Review.tags, Review.efficiency)
        .where(Review.platform == platform, Review.efficiency != PENDING_EFFICIENCY)
        .order_by(Review.created_at.asc())
    ).mappings().all()
    return _tally_tag_efficiency(_first_judged_rows([dict(r) for r in rows]))


# 재계산 주기. 전면 스캔 + 쓰기 트랜잭션이라 매 요청 돌 수는 없고, `_bump_tag_stats` 가
# 이 사이를 증분으로 메운다. 즉 표는 최대 이 시간만큼 뒤처진다. `/api/stats`·`/api/report`
# 는 사용자가 페이지를 열 때만 부르는 경로라 이 주기의 스캔 비용은 무시할 수 있다.
_TAG_STATS_RECONCILE_SEC = 60
_tag_stats_reconciled_at: float | None = None
# 쿨다운 확인과 갱신 사이를 보호한다 — 없으면 콜드 스타트에 동시 요청 N 개가 전부 전면
# 스캔 + 전면 재기록을 수행한다(db/connection.py 의 엔진 싱글턴과 같은 이유의 락이다).
_tag_stats_lock = threading.Lock()
# 표가 비어 있을 때만 이만큼 기다린다. 전면 스캔은 3만 행에서 1초 미만이라, 이 상한에
# 걸리는 것은 재계산이 아니라 DB 자체가 느려진 경우다.
_TAG_STATS_LOCK_WAIT_SEC = 5


def reset_tag_stats_rebuild_flag() -> None:
    """프로세스 로컬 재계산 쿨다운을 되돌린다. 테스트에서 DB 를 갈아끼울 때 쓴다."""
    global _tag_stats_reconciled_at
    _tag_stats_reconciled_at = None


def _reconcile_tag_stats() -> None:
    """tag_stats 를 reviews 에서 통째로 다시 계산해 덮어쓴다.

    tag_stats 는 `_first_submission_tag_counts(session, "boj")` 의 캐시다. 증분 갱신
    (`_bump_tag_stats`)은 리뷰 저장 경로만 지나가므로 백필·마이그레이션·직접 INSERT 로
    들어온 행은 반영되지 않는다. 그래서 캐시는 비어 있는 상태뿐 아니라 **부분적으로
    틀린** 상태로도 존재할 수 있다.

    "비어 있을 때만 채우기" 로는 그 부분 상태를 벗어나지 못한다 — 백필 500건 + 빈 표
    상태에서 새 리뷰 1건이 들어오면 표가 그 1건짜리(`math: 1`)로 굳고, 표가 비어 있지
    않으므로 다시는 복원되지 않는다. 전면 재계산은 어떤 상태에서 시작하든 정답으로
    수렴하므로 그 함정이 없다.
    """
    with session_scope(commit=True) as session:
        counts = _first_submission_tag_counts(session, "boj")
        # tag 순으로 읽는다 — 읽는 순서 자체가 잠금을 잡지는 않지만(FOR UPDATE 가 아니다),
        # 이 dict 의 순회 순서가 아래 delete 의 순서가 되므로 실행마다 같아진다.
        existing = {row.tag: row for row in
                    session.scalars(select(TagStat).order_by(TagStat.tag)).all()}
        for tag, c in counts.items():
            row = existing.pop(tag, None)
            if row is None:
                session.add(TagStat(tag=tag, good_count=c["good_count"],
                                    poor_count=c["poor_count"],
                                    total_count=c["total_count"]))
            else:
                row.good_count = c["good_count"]
                row.poor_count = c["poor_count"]
                row.total_count = c["total_count"]
        for row in existing.values():
            # reviews 에서 사라진 태그(행 삭제·태그 수정)의 잔재를 남기지 않는다.
            session.delete(row)


def get_tag_stats() -> list:
    """BOJ 태그별 good/poor 집계.

    tag_stats 는 `_bump_tag_stats` 가 **BOJ 첫 제출에서만** 채우는 비정규화 테이블이라,
    그 경로를 타지 않고 들어온 행(마이그레이션·백필·직접 INSERT)만 있으면 비어 있다.
    그러면 BOJ 리뷰가 아무리 많아도 `/api/report` 가 "아직 저장된 기록이 없습니다"(400)를
    내고 `/api/stats` 의 태그 통계도 빈다.

    그래서 이 경로가 표를 **주기적으로 전면 재계산**한다(`_reconcile_tag_stats`). 읽을
    때마다 폴백을 계산하는 방식은 스위치가 all-or-nothing 이라 새 리뷰 1건에 통계가
    붕괴하고, "비어 있을 때만 복원" 은 그 붕괴한 상태에서 빠져나오지 못한다.
    """
    global _tag_stats_reconciled_at
    def _read():
        with session_scope() as session:
            return [
                {"tag": r.tag, "good_count": r.good_count,
                 "poor_count": r.poor_count, "total_count": r.total_count}
                for r in session.scalars(
                    select(TagStat).order_by(TagStat.total_count.desc())).all()
            ]

    rows = _read()
    # 재계산은 한 번에 하나만 돈다. 표가 이미 차 있으면 기다리지 않는다 — 최대
    # _TAG_STATS_RECONCILE_SEC 만큼 뒤처진 값이라도 응답을 지연시키는 것보다 낫다.
    # 표가 **비어 있으면** 기다린다. 그 상태로 응답하면 /api/report 가 400 "아직 저장된
    # 기록이 없습니다", /api/stats 가 "아직 데이터가 없습니다" 로 나가, 리뷰 기록이 있는
    # 사용자가 기록이 없다는 화면을 본다.
    if rows:
        acquired = _tag_stats_lock.acquire(blocking=False)
    else:
        acquired = _tag_stats_lock.acquire(timeout=_TAG_STATS_LOCK_WAIT_SEC)
    if not acquired:
        return rows
    try:
        now = time.monotonic()
        if (_tag_stats_reconciled_at is not None
                and now - _tag_stats_reconciled_at < _TAG_STATS_RECONCILE_SEC):
            # 기다리는 동안 다른 스레드가 채웠을 수 있다 — 대기 전에 읽은 값이 아니라
            # 지금 값을 돌려준다.
            return _read()
        try:
            _reconcile_tag_stats()
        except DBAPIError as e:
            # 다른 인스턴스와 같은 행을 동시에 건드리면 PK 충돌·잠금 경합으로 진다.
            # 재계산은 멱등이라 다음 주기가 다시 맞춘다. 다만 OperationalError 도
            # DBAPIError 라, 예외를 버리면 진짜 DB 장애가 "경합" 한 줄로 사라진다.
            logger.warning("tag_stats 재계산 실패 — 다음 주기에 다시 맞춘다: %s", e)
        _tag_stats_reconciled_at = now
    finally:
        _tag_stats_lock.release()
    return _read()


def get_total_review_count(platform: str | None = None) -> int:
    """고유 문제 수. platform 을 주지 않으면 두 플랫폼을 합쳐 센다.

    problem_ref 는 플랫폼별 네임스페이스다(BOJ 는 숫자, CF 는 `4A` 꼴) — 합칠 때는
    platform 을 함께 distinct 해야 두 플랫폼의 같은 문자열이 하나로 합쳐지지 않는다.
    """
    with session_scope() as session:
        # `||` 연결을 쓴다 — func.concat 은 SQLite 3.44(2023-11)+ 에서만 있어서,
        # 그보다 낮은 런타임에서는 "no such function: concat" 이 난다.
        stmt = select(func.count(distinct(Review.platform + ":" + Review.problem_ref)))
        if platform:
            stmt = stmt.where(Review.platform == platform.strip().lower())
        return session.scalar(stmt)


def _tally_tag_efficiency(rows: list) -> dict:
    """행 목록을 태그별로 순회해 good/poor/total 카운트를 누적한 dict를 반환."""
    counts: dict[str, dict] = {}
    for row in rows:
        eff = row["efficiency"]
        if eff == PENDING_EFFICIENCY:
            continue  # 리뷰 대기 행은 good/poor 판정이 없다
        tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else (row["tags"] or [])
        for tag in tags:
            if tag not in counts:
                counts[tag] = {"tag": tag, "good_count": 0, "poor_count": 0, "total_count": 0}
            counts[tag]["total_count"] += 1
            if eff == "good":
                counts[tag]["good_count"] += 1
            else:
                counts[tag]["poor_count"] += 1
    return counts


def get_cf_tag_stats() -> list:
    with session_scope() as session:
        rows = [dict(r) for r in session.execute(
            select(Review.tags, Review.efficiency).where(Review.platform == "codeforces")
        ).mappings().all()]

    counts = _tally_tag_efficiency(rows)
    return sorted(counts.values(), key=lambda x: x["total_count"], reverse=True)


_AVG_TIER_WINDOW = 30  # UI 표시("최근 30개")와 일치


def get_average_tier() -> float:
    """최근 30개 고유 **BOJ** 문제의 tier 평균 — 성장에 따라 추천 난이도가 올라간다.

    플랫폼을 명시한다. `tier > 0` 만으로도 지금은 CF 가 걸러지지만(clients/codeforces.py
    가 CF 리뷰에 항상 tier=0 을 넣는다) 그건 우연이다 — CF 레이팅을 티어로 매핑하는
    변경이 들어오면 BOJ 평균 티어와 추천 난이도가 조용히 오염된다.
    형제 함수 get_tier_history·get_average_cf_rating 은 이미 플랫폼을 명시한다.
    """
    rn = func.row_number().over(
        partition_by=(Review.platform, Review.problem_ref),
        order_by=Review.created_at.desc(),
    ).label("rn")
    with session_scope() as session:
        sub = select(Review.tier, Review.created_at, rn).where(
            Review.platform == "boj", Review.tier > 0).subquery()
        tiers = session.scalars(
            select(sub.c.tier).where(sub.c.rn == 1)
            .order_by(sub.c.created_at.desc()).limit(_AVG_TIER_WINDOW)
        ).all()

    if not tiers:
        # 등급 있는 기록이 없다. 추천 난이도의 기본값으로 쓰라고 주는 값이지 **표시값이
        # 아니다** — 그대로 화면에 쓰면 기록이 없는 사용자에게 "Silver I" 가 뜬다.
        # 호출부는 has_graded_tier() 로 구분한다.
        return 10.0
    return sum(tiers) / len(tiers)


def has_graded_tier() -> bool:
    """등급(tier > 0)이 있는 BOJ 리뷰가 하나라도 있는지."""
    # 존재만 보면 되므로 LIMIT 1 이다 — COUNT 는 조건에 맞는 행을 전부 센다(5만 행에서 37ms).
    with session_scope() as session:
        return session.scalar(
            select(Review.id).where(Review.platform == "boj", Review.tier > 0).limit(1)) is not None


def get_problems_grouped(q: str = "", platform: str = "", tier_min: int | None = None,
                         tier_max: int | None = None, eff: str = "",
                         sort: str = "recent", page: int = 1,
                         per_page: int = DEFAULT_PAGE_SIZE) -> dict:
    """문제 단위로 접은 리뷰 기록 **한 페이지**. `{"problems": [...], "total": N}`.

    필터·정렬·페이지를 전부 SQL 에서 한다. 전 행을 파이썬으로 끌어와 접으면 응답 크기와
    메모리가 리뷰 수에 비례해 자란다(실측: 리뷰 1만 행 → 444ms·1.41MB, 5만 행 →
    5,575ms·7.37MB·피크 76.6MB). 화면은 한 번에 20건만 보여준다.

    난이도 그룹(bronze/silver/…)의 정의는 **프론트에 한 벌만** 둔다 — 호출부가 그 경계를
    tier_min/tier_max 로 풀어서 보낸다. 서버가 같은 표를 또 가지면 두 벌이 갈린다.
    """
    page, per_page = paging_bounds(page, per_page)

    # (platform, problem_ref) 로 묶는다 — 재제출 사이 제목/태그가 바뀌어도 한 문제다.
    part = (Review.platform, Review.problem_ref)
    latest = func.row_number().over(partition_by=part,
                                    order_by=Review.created_at.desc()).label("rn")
    total_rounds = func.count().over(partition_by=part).label("submission_count")
    last_at = func.max(Review.created_at).over(partition_by=part).label("last_submitted")

    ranked = select(
        Review.problem_id, Review.platform, Review.problem_ref, Review.title,
        Review.tier, Review.tier_name, Review.tags,
        Review.efficiency.label("last_efficiency"),
        latest, total_rounds, last_at,
    ).subquery()

    stmt = select(ranked).where(ranked.c.rn == 1)
    if platform:
        stmt = stmt.where(ranked.c.platform == platform.strip().lower())
    if tier_min is not None:
        stmt = stmt.where(ranked.c.tier >= tier_min)
    if tier_max is not None:
        stmt = stmt.where(ranked.c.tier <= tier_max)
    if eff:
        stmt = stmt.where(ranked.c.last_efficiency == eff)
    if (q or "").strip():
        stmt = stmt.where(search_filter(
            (ranked.c.title, ranked.c.problem_ref, ranked.c.tags), q))

    order = {
        "tier_desc": (ranked.c.tier.desc(), ranked.c.problem_ref.asc()),
        "tier_asc": (ranked.c.tier.asc(), ranked.c.problem_ref.asc()),
        # 번호순은 problem_id(정수)로 센다 — problem_ref 는 문자열이라 `1000` 이 `999`
        # 보다 앞선다. CF 는 problem_id 가 0 이라 한 덩어리로 묶이고, 그 안에서만
        # problem_ref 로 갈린다("1700A" < "1700B").
        "pid_asc": (ranked.c.problem_id.asc(), ranked.c.problem_ref.asc()),
    }.get(sort, (ranked.c.last_submitted.desc(), ranked.c.problem_ref.asc()))

    with session_scope() as session:
        if not (platform or eff or (q or "").strip()
                or tier_min is not None or tier_max is not None):
            # 필터가 없으면 "문제 수" 가 곧 전체 수다 — 좁은 DISTINCT 로 센다.
            # 윈도우 서브쿼리를 세면 같은 값을 얻는 데 50배 넘게 든다(실측 3ms vs 160ms).
            total = session.scalar(
                select(func.count(distinct(Review.platform + ":" + Review.problem_ref))))
        else:
            # 필터는 **최신 회차의 값**에 걸린다 — 어느 회차든 맞으면 되는 DISTINCT 로
            # 세면 수가 달라진다(재제출 사이 제목·티어·판정이 바뀌는 경우).
            total = session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = session.execute(
            stmt.order_by(*order).limit(per_page).offset((page - 1) * per_page)
        ).mappings().all()

    problems = []
    for r in rows:
        item = {k: v for k, v in r.items() if k != "rn"}
        problems.append(normalize_common_row(item))
    return {"problems": problems, "total": total or 0}


def get_reviews_by_problem(platform: str, problem_ref: str) -> list:
    with session_scope() as session:
        rows = session.execute(
            select(Review.id, Review.problem_id, Review.platform, Review.problem_ref, Review.title,
                   Review.tier, Review.tier_name, Review.tags, Review.code, Review.efficiency,
                   Review.complexity, Review.better_algorithm, Review.strengths, Review.weaknesses,
                   Review.feedback, Review.language, Review.problem_statement,
                   Review.created_at)
            .where(Review.platform == platform, Review.problem_ref == problem_ref)
            .order_by(Review.created_at.desc())
        ).mappings().all()
    result = [dict(r) for r in rows]
    for r in result:
        _normalize_review_row(r)
    return result


def get_problems_missing_statement(platform: str | None = None) -> list:
    """problem_statement 가 빈 행이 있는 문제를 (platform, problem_ref) 단위로 모아 반환한다.

    본문은 문제 단위로 같으므로 회차마다 다시 수집하지 않는다. `empty_rows` 는 dry-run 이
    "몇 행을 채울 예정" 을 보여주는 데 쓴다.

    최근 회차 순으로 정렬해 그룹핑하므로 결과도 그 순서를 유지한다.
    """
    with session_scope() as session:
        stmt = (select(Review.platform, Review.problem_ref)
                .where(Review.problem_statement == "")
                .order_by(Review.created_at.desc()))
        if platform:
            stmt = stmt.where(Review.platform == platform)
        rows = session.execute(stmt).mappings().all()

    grouped: dict[tuple[str, str], dict] = {}
    for r in rows:
        key = (r["platform"], r["problem_ref"])
        g = grouped.setdefault(key, {
            "platform": r["platform"], "problem_ref": r["problem_ref"], "empty_rows": 0,
        })
        g["empty_rows"] += 1
    return list(grouped.values())


def set_problem_statement(platform: str, problem_ref: str, statement: str) -> int:
    """해당 문제의 problem_statement 가 빈 행을 모두 채우고 갱신 행 수를 반환한다.

    이미 값이 있는 행은 건드리지 않는다 — 사용자가 직접 붙여 넣은 원문을 백필 값으로
    덮어쓰면 안 된다.
    """
    if not statement:
        return 0
    with session_scope(commit=True) as session:
        result = session.execute(
            update(Review)
            .where(Review.platform == platform, Review.problem_ref == problem_ref,
                   Review.problem_statement == "")
            .values(problem_statement=statement))
        return result.rowcount or 0


def get_tier_history() -> list:
    """성장 곡선용 — **문제당 첫 등장 한 점씩**, created_at 오름차순.

    tier 는 회차가 아니라 문제의 속성이라 값은 어느 회차를 골라도 같고, 바뀌는 건 그 문제가
    시계열에 놓이는 날짜뿐이다. 마지막 회차를 남기면 예전 문제를 재제출할 때 그 점이
    과거에서 사라져 오늘로 옮겨가고, 이미 지나간 구간의 레이팅이 소급 변한다.

    dedup 을 SQL 에서 한다 — 전 회차를 보내면 소비처(tier-chart.js)가 버릴 행까지
    전송·파싱한다(실측: 리뷰 1만 행에서 1.88MB, 회차가 늘수록 선형으로 자란다).
    """
    rn = func.row_number().over(
        partition_by=(Review.platform, Review.problem_ref),
        order_by=Review.created_at.asc()).label("rn")
    ranked = select(Review.problem_id, Review.platform, Review.problem_ref, Review.title,
                    Review.tier, Review.tier_name, Review.created_at, rn).where(
        Review.platform == "boj", Review.tier > 0).subquery()
    with session_scope() as session:
        rows = session.execute(
            select(ranked.c.problem_id, ranked.c.platform, ranked.c.problem_ref,
                   ranked.c.title, ranked.c.tier, ranked.c.tier_name, ranked.c.created_at)
            .where(ranked.c.rn == 1)
            .order_by(ranked.c.created_at.asc())
        ).mappings().all()
    return [dict(r) for r in rows]


def get_review_history(limit: int = 10, platform: str | None = None) -> list:
    with session_scope() as session:
        stmt = select(Review.id, Review.problem_id, Review.platform, Review.problem_ref,
                      Review.title, Review.tier, Review.tier_name, Review.tags,
                      Review.efficiency, Review.created_at)
        if platform:
            stmt = stmt.where(Review.platform == platform.strip().lower())
        stmt = stmt.order_by(Review.created_at.desc()).limit(limit)
        rows = session.execute(stmt).mappings().all()
    result = [dict(r) for r in rows]
    for r in result:
        normalize_common_row(r)
    return result


def get_average_cf_rating() -> float:
    """최근 30개 고유 문제의 CF 레이팅 평균 — get_average_tier 와 동일한 윈도우(static/js/recommend.js 라벨과 일치)."""
    rn = func.row_number().over(
        partition_by=Review.problem_ref, order_by=Review.created_at.desc()).label("rn")
    with session_scope() as session:
        sub = select(Review.tier_name, Review.created_at, rn).where(Review.platform == "codeforces").subquery()
        names = session.scalars(
            select(sub.c.tier_name).where(sub.c.rn == 1)
            .order_by(sub.c.created_at.desc()).limit(_AVG_TIER_WINDOW)
        ).all()

    ratings = []
    for tn in names:
        if tn and tn.startswith("Codeforces "):
            try:
                ratings.append(int(tn.split()[-1]))
            except ValueError:
                pass
    return sum(ratings) / len(ratings) if ratings else 1200.0


def get_tag_weakness_data(platform: str) -> list:
    """추천이 쓰는 태그별 (풀이 수, 마지막 풀이일, poor 비율).

    poor 비율은 `tag_stats` 를 **읽지 않고** reviews 에서 직접 센다. tag_stats 의 재계산을
    트리거하는 것은 `get_tag_stats()` 뿐이고 그것은 `/api/stats`·`/api/report` 에서만
    불린다 — 추천만 쓰는 프로세스는 재계산을 한 번도 돌지 않으므로, 여기서 표를 읽으면
    낡은 값이 인스턴스 수명 내내 유지된다. 그 값은 `recommender._score_tags` 에 가중치
    0.3 으로 들어가 추천 문제 선정을 바꾼다.

    poor 비율의 모집단은 그 플랫폼의 통계 화면과 같다 — BOJ 는 tag_stats 와 같은
    "문제당 첫 판정 행", CF 는 get_cf_tag_stats 와 같은 "전 회차".
    solve_count 는 회차가 아니라 **문제 수**를 센다(리뷰 기록 + 가져온 기록 합집합).
    """
    with session_scope() as session:
        rstmt = (select(Review.problem_ref, Review.tags, Review.efficiency, Review.created_at)
                 .where(Review.platform == platform)
                 .order_by(Review.created_at.asc()))   # _first_judged_rows 가 순서를 요구한다
        sstmt = (select(SolvedHistory.problem_ref, SolvedHistory.tags, SolvedHistory.imported_at)
                 .where(SolvedHistory.platform == platform))
        review_rows = [dict(r) for r in session.execute(rstmt).mappings().all()]
        solved_rows = [dict(r) for r in session.execute(sstmt).mappings().all()]

    # solve_count 는 **문제 수**다. 전 회차를 세면 같은 문제를 여러 번 고쳐 올린 태그일수록
    # 수가 부풀어 recommender._score_tags 의 count_score(가중치 0.5)에서 "덜 취약" 으로
    # 평가된다 — 가장 많이 고쳐 쓴, 즉 가장 어려워한 태그가 추천에서 밀리는 방향이다.
    tag_data = {}
    seen_refs: dict[str, set] = {}

    def _tally(tags, ref, date):
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
                seen_refs[tag] = set()
            if ref not in seen_refs[tag]:
                seen_refs[tag].add(ref)
                tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    for row in review_rows:
        _tally(json.loads(row["tags"]), row["problem_ref"], row.get("created_at", ""))
    for row in solved_rows:
        _tally(json.loads(row["tags"]), row["problem_ref"], row.get("imported_at", ""))

    # 위에서 이미 읽어온 행으로 센다 — 같은 테이블을 다시 스캔하지 않는다.
    counted = _first_judged_rows(review_rows) if platform == "boj" else review_rows
    poor_map = {tag: counts["poor_count"] / counts["total_count"]
                for tag, counts in _tally_tag_efficiency(counted).items()
                if counts["total_count"] > 0}

    return [
        {
            "tag": tag,
            "solve_count": data["count"],
            "last_solved_at": data["last_date"],
            "poor_ratio": poor_map.get(tag, 0.0),
        }
        for tag, data in tag_data.items()
    ]
