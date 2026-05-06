import os
import db
import clients as api_client
import analyzer
from fastapi import APIRouter, HTTPException
from routes.models import ReviewResponse

router = APIRouter()


@router.post("/api/review-imported/{platform}/{problem_ref}")
def review_imported(platform: str, problem_ref: str):
    if not os.environ.get("OPENAI_API_KEY"):
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

    db.save_review(
        problem_id=problem_info["id"],
        title=problem["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem["tags"],
        code=problem["code"],
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        platform=platform,
        problem_ref=problem_ref,
    )
    db.delete_solved_problem(platform, problem_ref)

    return ReviewResponse(
        problem_id=problem_info["id"],
        platform=platform,
        problem_ref=problem_ref,
        problem_url=api_client.get_problem_url(platform, problem_ref),
        title=problem["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem["tags"],
        efficiency=result["efficiency"],
        complexity=result.get("complexity", "N/A"),
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )


@router.delete("/api/solved-history/{platform}/{problem_ref}")
def delete_solved_history(platform: str, problem_ref: str):
    db.delete_solved_problem(platform, problem_ref)
    return {"ok": True}


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
