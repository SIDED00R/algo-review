import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from routes.models import ReviewRequest, ReviewResponse
from routes.problem_resolve import resolve_problem_info, resolve_statement
from routes.review_response import save_and_build_response
from demo_mode import IS_DEMO, DEMO_PROBLEM_INFO, DEMO_REVIEW_RESULT

router = APIRouter()


@router.post("/api/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")

    if IS_DEMO:
        return save_and_build_response(DEMO_PROBLEM_INFO, req.code, DEMO_REVIEW_RESULT, req.language)

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem_info = resolve_problem_info(req.platform, req.problem_id, req.problem_ref)
    statement = resolve_statement(req.platform, problem_info, req.problem_statement)

    try:
        result = analyzer.analyze_code(problem_info, statement, req.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    return save_and_build_response(problem_info, req.code, result, req.language)
