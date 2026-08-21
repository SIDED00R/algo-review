import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from routes.models import ReviewRequest, ReviewResponse
from routes.problem_resolve import resolve_problem_info, resolve_statement
from routes.helpers import require_language, upstream_failure
from routes.review_response import save_and_build_response
from demo_mode import IS_DEMO, DEMO_PROBLEM_INFO, DEMO_REVIEW_RESULT

router = APIRouter()


@router.post("/api/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")
    language = require_language(req.language)

    if IS_DEMO:
        return save_and_build_response(DEMO_PROBLEM_INFO, req.code, DEMO_REVIEW_RESULT,
                                      language, req.problem_statement or "")

    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem_info = resolve_problem_info(req.platform, req.problem_id, req.problem_ref)
    statement = resolve_statement(req.platform, problem_info, req.problem_statement)

    try:
        result = analyzer.analyze_code(problem_info, statement, req.code)
    except ValueError as e:
        # analyzer 가 직접 만든 사용자용 안내(토큰 초과·빈 응답)는 그대로 보여준다.
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise upstream_failure("코드 분석 실패", e)

    # 저장하는 것은 사용자가 붙여 넣은 원문(req.problem_statement)이다 — 위 statement 는
    # 스크래핑 결과가 섞여 있고, 재제출 때 resolve_statement 가 다시 해석한다.
    return save_and_build_response(problem_info, req.code, result, language,
                                   req.problem_statement or "")
