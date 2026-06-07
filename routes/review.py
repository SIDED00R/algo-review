import os
import db
import clients as api_client
import analyzer
from fastapi import APIRouter, HTTPException
from routes.models import ReviewRequest, ReviewResponse
from routes.review_response import save_and_build_response
from demo_mode import IS_DEMO, DEMO_PROBLEM_INFO, DEMO_REVIEW_RESULT

router = APIRouter()


def _resolve_problem(platform: str, problem_id: int | None, problem_ref: str | None,
                     custom_statement: str | None = None) -> tuple[dict, str]:
    platform = (platform or "boj").strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다. 'boj' 또는 'codeforces'만 가능합니다.")

    if platform == "codeforces":
        if not (problem_ref or "").strip():
            raise HTTPException(status_code=400, detail="Codeforces 문제 번호를 입력하세요. 예: 4A 또는 4/A")
        try:
            info = api_client.get_codeforces_problem_info(problem_ref.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Codeforces 문제 조회 실패: {e}")
        statement = (custom_statement or "").strip() or api_client.get_codeforces_problem_statement(info["problem_ref"])
        return info, statement

    if problem_id is None:
        raise HTTPException(status_code=400, detail="백준 문제 번호를 입력하세요.")

    info = db.get_cached_problem_info(problem_id)
    if not info:
        try:
            info = api_client.get_problem_info(problem_id)
        except Exception:
            info = {
                "id": problem_id,
                "platform": "boj",
                "problem_ref": str(problem_id),
                "title": f"문제 {problem_id}",
                "tier": 0,
                "tier_name": "Unrated",
                "tags": [],
            }
    info["platform"] = "boj"
    info["problem_ref"] = str(problem_id)
    statement = (custom_statement or "").strip() or api_client.get_problem_statement(problem_id)
    return info, statement


@router.post("/api/review", response_model=ReviewResponse)
def review_code(req: ReviewRequest):
    if IS_DEMO:
        return save_and_build_response(DEMO_PROBLEM_INFO, req.code, DEMO_REVIEW_RESULT)

    if not os.environ.get("OPENAI_API_KEY"):
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")

    problem_info, statement = _resolve_problem(req.platform, req.problem_id, req.problem_ref, req.problem_statement)

    try:
        result = analyzer.analyze_code(problem_info, statement, req.code)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    return save_and_build_response(problem_info, req.code, result)
