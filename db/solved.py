import json

from sqlalchemy import case, delete, func, select
from sqlalchemy.exc import IntegrityError

from db.connection import session_scope
from db.models import Review, SolvedHistory
from db.normalize import normalize_common_row, resolve_tier_name
from db.paging import DEFAULT_PAGE_SIZE, paging_bounds, search_filter
from timestamps import utc_now_iso


def _row_to_dict(obj) -> dict:
    return {col.name: getattr(obj, col.name) for col in obj.__table__.columns}


def save_solved_problem(problem_id: int, title: str, tier: int, tags: list,
                        code: str = "", language: str = "", platform: str = "boj",
                        problem_ref: str | None = None, tier_name: str = "",
                        imported_at: str = ""):
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()
    with session_scope() as session:
        if session.get(SolvedHistory, {"platform": platform, "problem_ref": problem_ref}) is not None:
            return  # (platform, problem_ref) 중복 — 최초 값 유지
        session.add(SolvedHistory(
            problem_id=problem_id, platform=platform, problem_ref=problem_ref,
            title=title, tier=tier, tier_name=tier_name,
            tags=json.dumps(tags, ensure_ascii=False), code=code, language=language,
            imported_at=imported_at or utc_now_iso(),
        ))
        try:
            session.commit()
        except IntegrityError:
            session.rollback()  # 동시 삽입 경합 — 이미 존재하면 무시


def claim_solved_problem(platform: str, problem_ref: str) -> dict | None:
    """가져온 기록 하나를 **선점**한다 — 성공하면 그 행을 돌려주고 표에서 지운다.

    조회와 삭제를 한 트랜잭션의 단일 DELETE 로 묶는다. 나누면 여러 요청이 전부 조회를
    통과해 각자 유료 LLM 호출을 하고 리뷰 행을 남긴다(그 문제의 제출 회차가 1이 아니라
    N 이 된다). 프론트의 진행 중 가드는 탭 로컬이라 두 탭에서 우회된다.

    선점에 실패하면(다른 요청이 먼저 집었거나 원래 없다) None 이다. 리뷰가 실패하면
    호출부가 `save_solved_problem` 으로 되돌린다.
    """
    platform = (platform or "boj").strip().lower()
    problem_ref = str(problem_ref).strip()
    with session_scope(commit=True) as session:
        # RETURNING 으로 조회와 삭제를 한 문장에 묶는다 — 나누면 여러 요청이 전부 조회를
        # 통과한다. SQLite 3.35+ 와 PostgreSQL 모두 DELETE ... RETURNING 을 지원한다.
        row = session.execute(
            delete(SolvedHistory)
            .where(SolvedHistory.platform == platform,
                   SolvedHistory.problem_ref == problem_ref)
            .returning(*SolvedHistory.__table__.columns)
        ).mappings().first()
    if row is None:
        return None
    return normalize_common_row(dict(row))


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
    return normalize_common_row(row)


def get_solved_history(q: str = "", platform: str = "", tier_min: int | None = None,
                       tier_max: int | None = None, sort: str = "date-desc",
                       page: int = 1, per_page: int = DEFAULT_PAGE_SIZE) -> dict:
    """가져온 기록 **한 페이지**. `{"problems": [...], "total": N}`.

    필터·정렬·페이지를 SQL 에서 한다. 난이도 그룹 정의는 프론트 한 곳뿐이고 호출부가
    tier_min/tier_max 로 풀어서 보낸다. `code` 는 싣지 않고 `has_code` 만 준다.
    """
    page, per_page = paging_bounds(page, per_page)
    has_code = case((SolvedHistory.code != "", 1), else_=0).label("has_code")

    stmt = select(SolvedHistory.problem_id, SolvedHistory.platform, SolvedHistory.problem_ref,
                  SolvedHistory.title, SolvedHistory.tier, SolvedHistory.tier_name,
                  SolvedHistory.language, SolvedHistory.imported_at,
                  has_code)
    if platform:
        stmt = stmt.where(SolvedHistory.platform == platform.strip().lower())
    if tier_min is not None:
        stmt = stmt.where(SolvedHistory.tier >= tier_min)
    if tier_max is not None:
        stmt = stmt.where(SolvedHistory.tier <= tier_max)
    if (q or "").strip():
        stmt = stmt.where(search_filter(
            (SolvedHistory.title, SolvedHistory.problem_ref, SolvedHistory.tags), q))

    order = {
        # 번호순은 problem_id(정수)로 센다 — problem_ref 는 문자열이라 `1000` 이 `999`
        # 보다 앞선다(`get_problems_grouped` 의 pid_asc 와 같은 규약).
        "id-asc": (SolvedHistory.problem_id.asc(), SolvedHistory.problem_ref.asc()),
        "id-desc": (SolvedHistory.problem_id.desc(), SolvedHistory.problem_ref.desc()),
        "tier-desc": (SolvedHistory.tier.desc(), SolvedHistory.problem_ref.asc()),
        "tier-asc": (SolvedHistory.tier.asc(), SolvedHistory.problem_ref.asc()),
    }.get(sort, (SolvedHistory.imported_at.desc(), SolvedHistory.problem_ref.asc()))

    with session_scope() as session:
        total = session.scalar(select(func.count()).select_from(stmt.subquery()))
        rows = session.execute(
            stmt.order_by(*order).limit(per_page).offset((page - 1) * per_page)
        ).mappings().all()

    problems = []
    for r in rows:
        item = dict(r)
        normalize_common_row(item)
        item["has_code"] = bool(item["has_code"])
        problems.append(item)
    return {"problems": problems, "total": total or 0}


def get_solved_cf_refs() -> set:
    with session_scope() as session:
        refs = set(session.scalars(
            select(Review.problem_ref).where(Review.platform == "codeforces").distinct()).all())
        refs |= set(session.scalars(
            select(SolvedHistory.problem_ref).where(SolvedHistory.platform == "codeforces")).all())
    return refs


def get_solved_problem_ids() -> set:
    with session_scope() as session:
        # BOJ 전용이다 — 호출처가 전부 "이미 푼 BOJ 문제 번호 제외" 용도다.
        # CF 행의 problem_id 에 실제 값이 들어가면 그 번호의 BOJ 문제가 조용히 제외된다.
        ids = set(session.scalars(
            select(Review.problem_id).where(Review.platform == "boj").distinct()).all())
        ids |= set(session.scalars(
            select(SolvedHistory.problem_id).where(SolvedHistory.platform == "boj")).all())
    return ids


def get_solved_problem_keys() -> set[tuple[str, str]]:
    with session_scope() as session:
        keys = {(p, str(r)) for p, r in session.execute(
            select(Review.platform, Review.problem_ref).distinct()).all()}
        keys |= {(p, str(r)) for p, r in session.execute(
            select(SolvedHistory.platform, SolvedHistory.problem_ref)).all()}
    return keys
