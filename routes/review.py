import analyzer
from fastapi import APIRouter, HTTPException
from routes.models import ReviewRequest, ReviewResponse
from routes.problem_resolve import resolve_problem_info, resolve_statement
from routes.helpers import require_language, require_openai_key, run_llm
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

    require_openai_key()

    problem_info = resolve_problem_info(req.platform, req.problem_id, req.problem_ref)
    statement = resolve_statement(req.platform, problem_info, req.problem_statement)

    result = run_llm("코드 분석 실패", analyzer.analyze_code, problem_info, statement, req.code)

    # 저장하는 것은 사용자가 붙여 넣은 원문(req.problem_statement)이다 — 위 statement 는
    # 스크래핑 결과가 섞여 있고, 재제출 때 resolve_statement 가 다시 해석한다.
    return save_and_build_response(problem_info, req.code, result, language,
                                   req.problem_statement or "")
