import db
from fastapi import APIRouter, HTTPException
from routes.models import validate_platform

router = APIRouter()


@router.get("/api/reviews/grouped")
def list_reviews_grouped():
    return {"problems": db.get_problems_grouped()}


@router.get("/api/reviews/problem/{platform}/{problem_ref}")
def get_reviews_by_problem(platform: str, problem_ref: str):
    try:
        platform = validate_platform(platform)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"reviews": db.get_reviews_by_problem(platform, problem_ref)}
