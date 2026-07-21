import json
from datetime import datetime

from sqlalchemy import case, delete, select
from sqlalchemy.exc import IntegrityError

from db.connection import session_scope
from db.models import Review, SolvedHistory
from db.normalize import normalize_common_row, resolve_tier_name


def _normalize_solved_row(row: dict) -> dict:
    return normalize_common_row(row)


def _row_to_dict(obj) -> dict:
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


def save_solved_problem(problem_id: int, title: str, tier: int, tags: list,
                        code: str = "", language: str = "", platform: str = "boj",
                        problem_ref: str | None = None, tier_name: str = ""):
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()
    with session_scope() as session:
        if session.get(SolvedHistory, {"platform": platform, "problem_ref": problem_ref}) is not None:
            return  # (platform, problem_ref) 중복 — 최초 값 유지
        session.add(SolvedHistory(
            problem_id=problem_id, platform=platform, problem_ref=problem_ref,
            title=title, tier=tier, tier_name=tier_name,
            tags=json.dumps(tags, ensure_ascii=False), code=code, language=language,
            imported_at=datetime.now().isoformat(),
        ))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()  # 동시 삽입 경합 — 이미 존재하면 무시


def delete_solved_problem(platform: str, problem_ref: str):
    with session_scope(commit=True) as session:
        session.execute(delete(SolvedHistory).where(
            SolvedHistory.platform == platform, SolvedHistory.problem_ref == problem_ref))


def clear_solved_history():
    with session_scope(commit=True) as session:
        session.execute(delete(SolvedHistory))


def get_cached_problem_info(problem_id: int) -> dict | None:
    with session_scope() as session:
        row = session.execute(
            select(Review.title, Review.tier, Review.tier_name, Review.tags)
            .where(Review.platform == "boj", Review.problem_id == problem_id)
            .order_by(Review.created_at.desc()).limit(1)
        ).first()
        if row is None:
            row = session.execute(
                select(SolvedHistory.title, SolvedHistory.tier, SolvedHistory.tier_name, SolvedHistory.tags)
                .where(SolvedHistory.platform == "boj", SolvedHistory.problem_id == problem_id).limit(1)
            ).first()

    if row is None:
        return None

    title, tier, tier_name, tags_json = row
    tags = json.loads(tags_json) if tags_json else []
    return {
        "id": problem_id,
        "title": title,
        "tier": tier,
        "tier_name": resolve_tier_name(tier, tier_name),
        "tags": tags,
    }


def get_solved_problem(platform: str, problem_ref: str) -> dict | None:
    with session_scope() as session:
        obj = session.get(SolvedHistory, {"platform": platform, "problem_ref": problem_ref})
        if obj is None:
            return None
        row = _row_to_dict(obj)
    return _normalize_solved_row(row)


def get_solved_history() -> list:
    has_code = case((SolvedHistory.code != "", 1), else_=0).label("has_code")
    with session_scope() as session:
        rows = session.execute(
            select(SolvedHistory.problem_id, SolvedHistory.platform, SolvedHistory.problem_ref,
                   SolvedHistory.title, SolvedHistory.tier, SolvedHistory.tier_name,
                   SolvedHistory.language, SolvedHistory.imported_at, has_code)
            .order_by(SolvedHistory.imported_at.desc())
        ).mappings().all()
    result = [dict(r) for r in rows]
    for r in result:
        _normalize_solved_row(r)
        r["has_code"] = bool(r["has_code"])
    return result


def get_solved_cf_refs() -> set:
    with session_scope() as session:
        refs = set(session.scalars(
            select(Review.problem_ref).where(Review.platform == "codeforces").distinct()).all())
        refs |= set(session.scalars(
            select(SolvedHistory.problem_ref).where(SolvedHistory.platform == "codeforces")).all())
    return refs


def get_solved_problem_ids() -> set:
    with session_scope() as session:
        ids = set(session.scalars(select(Review.problem_id).distinct()).all())
        ids |= set(session.scalars(select(SolvedHistory.problem_id)).all())
    return ids


def get_solved_problem_keys() -> set[tuple[str, str]]:
    with session_scope() as session:
        keys = {(p, str(r)) for p, r in session.execute(
            select(Review.platform, Review.problem_ref).distinct()).all()}
        keys |= {(p, str(r)) for p, r in session.execute(
            select(SolvedHistory.platform, SolvedHistory.problem_ref)).all()}
    return keys
