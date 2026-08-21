import db
import analyzer
from fastapi import APIRouter, HTTPException
from config import settings
from demo_mode import IS_DEMO, demo_block
from routes.problem_resolve import resolve_problem_info, resolve_statement
from routes.review_response import save_and_build_response

router = APIRouter()


@router.post("/api/review-imported/{platform}/{problem_ref}")
def review_imported(platform: str, problem_ref: str):
    if IS_DEMO:
        demo_block("가져온 기록 AI 리뷰는 데모 버전에서 지원되지 않습니다.")
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    problem = db.get_solved_problem(platform, problem_ref)
    if not problem:
        raise HTTPException(status_code=404, detail="가져온 기록에서 해당 문제를 찾을 수 없습니다.")
    if not problem.get("code"):
        raise HTTPException(status_code=400, detail="저장된 코드가 없습니다. 세션 쿠키로 다시 가져오기 해주세요.")

    if platform == "codeforces":
        # 조회 실패를 400/500 으로 매핑하는 공용 해석기를 쓴다(직접 호출하면 ValueError 가 500 으로만 샌다).
        problem_info = resolve_problem_info("codeforces", None, problem_ref)
    else:
        problem_id = problem["problem_id"]
        problem_info = {
            "id": problem_id,
            "platform": "boj",
            "problem_ref": str(problem_id),
            "title": problem["title"],
            "tier": problem["tier"],
            "tier_name": problem["tier_name"],   # normalize_common_row 가 항상 채운다
            "tags": problem["tags"],
        }

    # 수집 함수는 예외 대신 실패 문자열을 반환한다 — 직접 부르면 그 값이 프롬프트의
    # 문제 설명 자리에 그대로 박힌다(acmicpc.net 종료 이후 BOJ 가 상시 이 상태였다).
    # 리뷰·재리뷰와 같은 해석기를 써서 실패를 빈 본문으로 바꾼다.
    statement = resolve_statement(platform, problem_info)

    try:
        result = analyzer.analyze_code(problem_info, statement, problem["code"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")

    # solved 기록의 제목/태그/식별자를 응답·저장 기준으로 사용한다. 단 빈 값으로 덮지
    # 않는다 — CF 는 제목·태그를 문제 조회에서 받아오므로 solved 행이 비어 있으면
    # 그걸 살려야 한다(BOJ 는 위에서 이미 같은 값으로 채워 no-op).
    problem_info["platform"] = platform
    problem_info["problem_ref"] = problem_ref
    if problem.get("title"):
        problem_info["title"] = problem["title"]
    if problem.get("tags"):
        problem_info["tags"] = problem["tags"]

    response = save_and_build_response(problem_info, problem["code"], result,
                                       problem.get("language", ""))
    db.delete_solved_problem(platform, problem_ref)
    return response


@router.delete("/api/solved-history")
def clear_solved_history():
    if IS_DEMO:
        demo_block("가져온 기록 삭제는 데모 버전에서 지원되지 않습니다.")
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
