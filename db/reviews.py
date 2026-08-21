import json
from datetime import datetime

from sqlalchemy import distinct, func, select

from db.connection import session_scope
from db.models import Review, SolvedHistory, TagStat
from db.normalize import normalize_common_row


PENDING_EFFICIENCY = "pending"
"""LLM 리뷰 없이 등록한 행의 효율성 마커.

good/ok/poor 판정이 없는 상태이므로 태그 통계 집계에서 제외한다 —
update_pending_review 가 실제 리뷰로 채울 때 집계한다.
"""


def _normalize_review_row(row: dict) -> dict:
    normalize_common_row(row)

    if isinstance(row.get("strengths"), str):
        row["strengths"] = json.loads(row.get("strengths") or "[]")
    else:
        row["strengths"] = row.get("strengths", [])
    if isinstance(row.get("weaknesses"), str):
        row["weaknesses"] = json.loads(row.get("weaknesses") or "[]")
    else:
        row["weaknesses"] = row.get("weaknesses", [])
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
            tags=json.dumps(tags, ensure_ascii=False), code=code, feedback=feedback,
            efficiency=efficiency, complexity=complexity, better_algorithm=better_algorithm or "",
            strengths=json.dumps(strengths, ensure_ascii=False),
            weaknesses=json.dumps(weaknesses, ensure_ascii=False),
            language=language, problem_statement=problem_statement or "",
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
        row.complexity = result.get("complexity", "")
        row.better_algorithm = result.get("better_algorithm") or ""
        row.feedback = result.get("feedback", "")
        row.strengths = json.dumps(result.get("strengths", []), ensure_ascii=False)
        row.weaknesses = json.dumps(result.get("weaknesses", []), ensure_ascii=False)

        if platform == "boj" and reviewed_before == 0:
            _bump_tag_stats(session, json.loads(row.tags), efficiency)
        return True


def get_tag_stats() -> list:
    with session_scope() as session:
        rows = session.scalars(select(TagStat).order_by(TagStat.total_count.desc())).all()
        return [
            {"tag": r.tag, "good_count": r.good_count,
             "poor_count": r.poor_count, "total_count": r.total_count}
            for r in rows
        ]


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
    """최근 30개 고유 문제의 tier 평균 — 성장에 따라 추천 난이도가 올라간다."""
    rn = func.row_number().over(
        partition_by=(Review.platform, Review.problem_ref),
        order_by=Review.created_at.desc(),
    ).label("rn")
    with session_scope() as session:
        sub = select(Review.tier, Review.created_at, rn).where(Review.tier > 0).subquery()
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
    order: list[tuple] = []
    for r in rows:
        key = (r["platform"], r["problem_ref"])
        if key not in grouped:
            grouped[key] = {
                "problem_id": r["problem_id"], "platform": r["platform"],
                "problem_ref": r["problem_ref"], "title": r["title"],
                "tier": r["tier"], "tier_name": r["tier_name"], "tags": r["tags"],
                "submission_count": 0, "last_submitted": r["created_at"], "_effs": [],
            }
            order.append(key)
        g = grouped[key]
        g["submission_count"] += 1
        g["_effs"].append(r["efficiency"])  # rows 가 created_at DESC 라 최신순으로 쌓인다

    result = []
    for key in order:
        g = grouped[key]
        g["efficiencies"] = ",".join(g.pop("_effs"))
        _normalize_review_row(g)
        result.append(g)
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
        _normalize_review_row(r)
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
                poor_map[tag] = 1 - counts["good_count"] / counts["total_count"]

    return [
        {
            "tag": tag,
            "solve_count": data["count"],
            "last_solved_at": data["last_date"],
            "poor_ratio": poor_map.get(tag, 0.0),
        }
        for tag, data in tag_data.items()
    ]
