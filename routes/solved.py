import db
import clients as api_client
import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from routes.review_response import save_and_build_response

router = APIRouter()


@router.post("/api/review-imported/{platform}/{problem_ref}")
def review_imported(platform: str, problem_ref: str):
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem = db.get_solved_problem(platform, problem_ref)
    if not problem:
        raise HTTPException(status_code=404, detail="가져온 기록에서 해당 문제를 찾을 수 없습니다.")
    if not problem.get("code"):
        raise HTTPException(status_code=400, detail="저장된 코드가 없습니다. 세션 쿠키로 다시 가져오기 해주세요.")

    if platform == "codeforces":
        problem_info = api_client.get_codeforces_problem_info(problem_ref)
        if problem.get("title"):
            problem_info["title"] = problem["title"]
        statement = api_client.get_codeforces_problem_statement(problem_ref)
    else:
        problem_id = problem["problem_id"]
        problem_info = {
            "id": problem_id,
            "platform": "boj",
            "problem_ref": str(problem_id),
            "title": problem["title"],
            "tier": problem["tier"],
            "tier_name": problem.get("tier_name") or api_client.TIER_NAMES.get(problem["tier"], "?"),
            "tags": problem["tags"],
        }
        statement = api_client.get_problem_statement(problem_id)

    try:
        result = analyzer.analyze_code(problem_info, statement, problem["code"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    # solved 기록의 제목/태그/식별자를 응답·저장 기준으로 사용
    problem_info["platform"] = platform
    problem_info["problem_ref"] = problem_ref
    problem_info["title"] = problem["title"]
    problem_info["tags"] = problem["tags"]

    response = save_and_build_response(problem_info, problem["code"], result)
    db.delete_solved_problem(platform, problem_ref)
    return response


@router.delete("/api/solved-history")
def clear_solved_history():
    db.clear_solved_history()
    return {"ok": True}


@router.get("/api/solved-history/{platform}/{problem_ref}")
def get_solved_history_detail(platform: str, problem_ref: str):
    p = db.get_solved_problem(platform, problem_ref)
    if not p:
        raise HTTPException(status_code=404, detail="없음")
    return {"code": p.get("code", "")}


@router.get("/api/solved-history")
def get_solved_history():
    rows = db.get_solved_history()
    return {"problems": rows}
