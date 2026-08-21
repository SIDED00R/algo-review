import db
from fastapi import APIRouter
from routes.helpers import require_platform

router = APIRouter()


@router.get("/api/reviews/grouped")
def list_reviews_grouped():
    return {"problems": db.get_problems_grouped()}


@router.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    platform = require_platform(platform)
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}
