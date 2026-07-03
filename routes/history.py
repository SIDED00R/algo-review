import db
from fastapi import APIRouter, HTTPException

router = APIRouter()


@router.get("/api/reviews/grouped")
def list_reviews_grouped():
    return {"problems": db.get_problems_grouped()}


@router.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    platform = platform.strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다.")
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}
