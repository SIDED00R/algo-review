import db
from fastapi import APIRouter, Query
from routes.helpers import require_platform

router = APIRouter()


@router.get("/api/reviews/grouped")
def list_reviews_grouped(
    q: str = Query(""),
    platform: str = Query(""),
    # 난이도 그룹(bronze/silver/…)의 경계는 프론트가 풀어서 보낸다 — 서버가 같은 표를
    # 또 가지면 두 벌이 갈린다. 그룹은 BOJ 티어 체계라 호출부가 platform=boj 도 함께 준다.
    tier_min: int | None = Query(None),
    tier_max: int | None = Query(None),
    eff: str = Query(""),
    sort: str = Query("recent"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1),
):
    return db.get_problems_grouped(q=q, platform=platform, tier_min=tier_min,
                                   tier_max=tier_max, eff=eff, sort=sort,
                                   page=page, per_page=per_page)


@router.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    platform = require_platform(platform)
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}
