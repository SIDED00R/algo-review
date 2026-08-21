import json
import logging
from datetime import datetime

from sqlalchemy import distinct, func, select, update
from sqlalchemy.exc import IntegrityError

from db.connection import session_scope
from db.models import Review, SolvedHistory, TagStat
from db.normalize import normalize_common_row

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
    """태그별 good/poor 카운트를 누적한다. BOJ 첫 리뷰에서만 호출한다."""
    for tag in tags:
        stat = session.get(TagStat, tag)
        if stat is None:
            stat = TagStat(tag=tag, good_count=0, poor_count=0, total_count=0)
            session.add(stat)
            session.flush()
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
            created_at=datetime.now().isoformat(),
        ))

        # tag_stats 는 BOJ 첫 제출에서만 집계한다. 리뷰 대기 행은 판정이 없어 제외한다.
        if is_first_submission and platform == "boj" and efficiency != PENDING_EFFICIENCY:
            _bump_tag_stats(session, tags, efficiency)


def update_pending_review(platform: str, problem_ref: str, result: dict) -> bool:
    """최신 '리뷰 대기' 행을 실제 리뷰 결과로 채운다. 대기 행이 없으면 False.

    행을 새로 쌓지 않으므로 제출 회차가 늘지 않는다. save_review 가 미룬 tag_stats 집계는
    이 문제의 첫 리뷰인 경우 여기서 수행한다.
    """
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or "").strip()

    with session_scope(commit=True) as session:
        row = session.scalars(
            select(Review)
            .where(Review.platform == platform, Review.problem_ref == problem_ref,
                   Review.efficiency == PENDING_EFFICIENCY)
            .order_by(Review.created_at.desc()).limit(1)
        ).first()
        if row is None:
            return False

        # row 를 고치기 전에 세야 한다 — 뒤로 옮기면 autoflush 로 자기 행이 포함된다.
        reviewed_before = session.scalar(
            select(func.count()).select_from(Review)
            .where(Review.platform == platform, Review.problem_ref == problem_ref,
                   Review.efficiency != PENDING_EFFICIENCY))

        efficiency = result["efficiency"]
        row.efficiency = efficiency
        # `or ""` 로 통일한다 — `.get(key, default)` 는 LLM 이 값에 null 을 준 경우
        # default 를 적용하지 않아 NOT NULL 컬럼에 None 이 들어간다(analyzer 가 이미
        # 정규화하지만, 이 함수는 dict 를 직접 받는 공개 경로라 여기서도 막는다).
        row.complexity = result.get("complexity") or ""
        row.better_algorithm = result.get("better_algorithm") or ""
        row.feedback = result.get("feedback") or ""
        # 리스트도 `or []` 로 통일한다 — json.dumps(None) 은 IntegrityError 없이
        # 문자열 "null" 을 만들어 통과하고, 읽을 때 None 이 되어 API 가 null 을 내보낸다.
        row.strengths = json.dumps(result.get("strengths") or [], ensure_ascii=False)
        row.weaknesses = json.dumps(result.get("weaknesses") or [], ensure_ascii=False)

        if platform == "boj" and reviewed_before == 0:
            _bump_tag_stats(session, json.loads(row.tags), efficiency)
        return True


def _first_submission_tag_counts(session) -> dict:
    """BOJ 리뷰에서 **문제당 첫 제출**만 세어 태그별 good/poor 를 만든다.

    `_bump_tag_stats` 와 같은 기준이다 — 다른 기준으로 복원하면 두 경로가 뒤집힐 때
    숫자가 튄다. `created_at` 오름차순으로 훑어 (platform, problem_ref) 첫 행만 쓴다.
    """
    rows = session.execute(
        select(Review.problem_ref, Review.tags, Review.efficiency)
        .where(Review.platform == "boj")
        .order_by(Review.created_at.asc())
    ).mappings().all()

    seen = set()
    firsts = []
    for row in rows:
        if row["problem_ref"] in seen:
            continue
        seen.add(row["problem_ref"])
        firsts.append(dict(row))
    return _tally_tag_efficiency(firsts)


def _rebuild_tag_stats() -> None:
    """비어 있는 tag_stats 를 reviews 에서 **한 번** 복원한다.

    읽기 경로에서 매번 폴백을 계산하면 스위치가 all-or-nothing 이라 통계가 튄다 —
    백필로 들어온 BOJ 리뷰 500건 + 빈 tag_stats 상태에서 새 리뷰 **1건**을 저장하면
    `_bump_tag_stats` 가 행 1개를 만들고, 다음 조회부터 폴백을 건너뛰어 `math: 120` 이
    `math: 1` 로 붕괴한다. 상태를 수렴시켜 스위치 자체를 없앤다.
    """
    with session_scope(commit=True) as session:
        if session.scalar(select(func.count()).select_from(TagStat)):
            return   # 다른 인스턴스가 먼저 채웠다
        for tag, counts in _first_submission_tag_counts(session).items():
            session.add(TagStat(tag=tag, good_count=counts["good_count"],
                                poor_count=counts["poor_count"],
                                total_count=counts["total_count"]))


def get_tag_stats() -> list:
    """BOJ 태그별 good/poor 집계.

    tag_stats 는 `_bump_tag_stats` 가 **BOJ 첫 제출에서만** 채우는 비정규화 테이블이라,
    그 경로를 타지 않고 들어온 행(마이그레이션·백필·직접 INSERT)만 있으면 비어 있다.
    그러면 BOJ 리뷰가 아무리 많아도 `/api/report` 가 "아직 저장된 기록이 없습니다"(400)를
    내고 `/api/stats` 의 태그 통계도 빈다.

    비어 있으면 **읽을 때마다 폴백을 계산하는 대신 테이블을 한 번 복원**한다. 폴백 방식은
    스위치가 all-or-nothing 이라, 복원 전 상태에서 새 리뷰 1건이 들어오는 순간 통계가
    붕괴한다(위 `_rebuild_tag_stats` docstring 참조).
    """
    def _read():
        with session_scope() as session:
            return [
                {"tag": r.tag, "good_count": r.good_count,
                 "poor_count": r.poor_count, "total_count": r.total_count}
                for r in session.scalars(
                    select(TagStat).order_by(TagStat.total_count.desc())).all()
            ]

    rows = _read()
    if rows:
        return rows
    try:
        _rebuild_tag_stats()
    except IntegrityError:
        # 두 인스턴스가 동시에 복원하면 한쪽이 진다 — 상대가 넣은 값을 읽으면 된다.
        logger.info("tag_stats 복원 경합 — 다른 인스턴스가 먼저 채웠다")
    return _read()


def get_total_review_count(platform: str | None = None) -> int:
    with session_scope() as session:
        stmt = select(func.count(distinct(Review.problem_ref)))
        if platform:
            stmt = stmt.where(Review.platform == platform.strip().lower())
        return session.scalar(stmt)


def _tally_tag_efficiency(rows: list) -> dict:
    """행 목록을 태그별로 순회해 good/poor/total 카운트를 누적한 dict를 반환."""
    counts: dict[str, dict] = {}
    for row in rows:
        eff = row.get("efficiency", "poor")
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
        return 10.0
    return sum(tiers) / len(tiers)


def get_problems_grouped() -> list:
    with session_scope() as session:
        rows = session.execute(
            select(Review.problem_id, Review.platform, Review.problem_ref, Review.title,
                   Review.tier, Review.tier_name, Review.tags, Review.efficiency, Review.created_at)
            .order_by(Review.created_at.desc())
        ).mappings().all()

    # (platform, problem_ref) 로 묶는다 — 재제출 사이 제목/태그가 바뀌어도 한 문제로 합쳐진다.
    grouped: dict[tuple, dict] = {}
    for r in rows:
        key = (r["platform"], r["problem_ref"])
        # rows 가 created_at DESC 라 처음 만난 행이 최신 회차다.
        g = grouped.setdefault(key, {
            "problem_id": r["problem_id"], "platform": r["platform"],
            "problem_ref": r["problem_ref"], "title": r["title"],
            "tier": r["tier"], "tier_name": r["tier_name"], "tags": r["tags"],
            "submission_count": 0, "last_submitted": r["created_at"],
            # 값 하나만 내려보낸다 — 소비처(history.js)가 최신 회차 배지에만 쓴다.
            # 목록을 CSV 로 만들면 판정 문자열에 콤마가 들어갈 때 깨진다.
            "last_efficiency": r["efficiency"],
        })
        g["submission_count"] += 1

    result = list(grouped.values())
    for g in result:
        normalize_common_row(g)
    return result


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
    with session_scope() as session:
        rows = session.execute(
            select(Review.problem_id, Review.platform, Review.problem_ref, Review.title,
                   Review.tier, Review.tier_name, Review.created_at)
            .where(Review.platform == "boj", Review.tier > 0)
            .order_by(Review.created_at.asc())
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
    with session_scope() as session:
        rstmt = select(Review.tags, Review.efficiency, Review.created_at).where(Review.platform == platform)
        sstmt = select(SolvedHistory.tags, SolvedHistory.imported_at).where(SolvedHistory.platform == platform)
        review_rows = [dict(r) for r in session.execute(rstmt).mappings().all()]
        solved_rows = [dict(r) for r in session.execute(sstmt).mappings().all()]

        # tag_stats는 BOJ 전용 — boj가 아닌 플랫폼이면 제외한다.
        if platform != "boj":
            stat_rows = []
        else:
            stat_rows = [dict(r) for r in session.execute(
                select(TagStat.tag, TagStat.poor_count, TagStat.total_count)).mappings().all()]

    tag_data = {}
    for row in review_rows:
        tags = json.loads(row["tags"])
        date = row.get("created_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    for row in solved_rows:
        tags = json.loads(row["tags"])
        date = row.get("imported_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    poor_map = {}
    if stat_rows:
        for s in stat_rows:
            if s["total_count"] > 0:
                poor_map[s["tag"]] = s["poor_count"] / s["total_count"]
    else:
        tag_eff = _tally_tag_efficiency(review_rows)
        for tag, counts in tag_eff.items():
            if counts["total_count"] > 0:
                # tag_stats 경로와 같은 식으로 쓴다 — _tally_tag_efficiency 가 pending 을
                # 건너뛰어 good + poor == total 이므로 수학적으로 동치지만, 읽는 사람이
                # 그 동치성을 매번 증명해야 하는 부채를 없앤다.
                poor_map[tag] = counts["poor_count"] / counts["total_count"]

    return [
        {
            "tag": tag,
            "solve_count": data["count"],
            "last_solved_at": data["last_date"],
            "poor_ratio": poor_map.get(tag, 0.0),
        }
        for tag, data in tag_data.items()
    ]
