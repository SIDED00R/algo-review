import db
import analyzer
from fastapi import APIRouter, HTTPException, Query
from config import settings
from demo_mode import IS_DEMO, demo_block
from routes.helpers import require_platform, require_reviewable_code, upstream_failure
from routes.problem_resolve import resolve_problem_info, resolve_statement
from routes.review_response import save_and_build_response

router = APIRouter()


@router.post("/api/review-imported/{platform}/{problem_ref}")
def review_imported(platform: str, problem_ref: str):
    if IS_DEMO:
        demo_block("가져온 기록 AI 리뷰는 데모 버전에서 지원되지 않습니다.")
    platform = require_platform(platform)
    if not settings.openai_api_key:
        raise HTTPException(status_code=500, detail="OPENAI_API_KEY가 설정되지 않았습니다.")

    # 조회-리뷰-삭제를 나누면 여러 요청이 전부 조회를 통과해 각자 유료 LLM 호출을 한다.
    # 삭제를 선점으로 써서 한 요청만 진행시킨다. 실패하면 아래에서 되돌린다.
    problem = db.claim_solved_problem(platform, problem_ref)
    if not problem:
        raise HTTPException(status_code=404, detail="가져온 기록에서 해당 문제를 찾을 수 없습니다.")

    def _restore():
        """선점한 행을 되돌린다 — 리뷰가 실패하면 목록에서 사라지면 안 된다."""
        db.save_solved_problem(
            problem["problem_id"], problem.get("title", ""), problem.get("tier", 0),
            problem.get("tags", []), code=problem.get("code", ""),
            language=problem.get("language", ""), platform=platform,
            problem_ref=problem_ref, tier_name=problem.get("tier_name", ""),
            imported_at=problem.get("imported_at", ""))

    try:
        if not problem.get("code"):
            raise HTTPException(status_code=400, detail="저장된 코드가 없습니다. 세션 쿠키로 다시 가져오기 해주세요.")
        require_reviewable_code(problem["code"])

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

        # 수집 함수는 예외 대신 실패 문자열을 반환한다 — 리뷰·재리뷰와 같은 해석기를 써서
        # 실패를 빈 본문으로 바꾼다.
        statement = resolve_statement(platform, problem_info)

        try:
            result = analyzer.analyze_code(problem_info, statement, problem["code"])
        except ValueError as e:
            raise HTTPException(status_code=502, detail=str(e))
        except Exception as e:
            raise upstream_failure("코드 분석 실패", e)
    except Exception:
        _restore()
        raise

    # solved 기록의 제목·태그·식별자를 쓰되 빈 값으로 덮지 않는다 — CF 는 문제 조회에서
    # 받아오므로 solved 행이 비어 있으면 그걸 살려야 한다.
    problem_info["platform"] = platform
    problem_info["problem_ref"] = problem_ref
    if problem.get("title"):
        problem_info["title"] = problem["title"]
    if problem.get("tags"):
        problem_info["tags"] = problem["tags"]

    # 행은 이미 선점 시점에 지웠다 — 여기서 또 지우면 그 사이 사용자가 다시 가져온
    # 같은 문제까지 지운다.
    return save_and_build_response(problem_info, problem["code"], result,
                                   problem.get("language", ""))


@router.delete("/api/solved-history")
def clear_solved_history():
    if IS_DEMO:
        demo_block("가져온 기록 삭제는 데모 버전에서 지원되지 않습니다.")
    db.clear_solved_history()
    return {"ok": True}


@router.get("/api/solved-history/{platform}/{problem_ref}")
def get_solved_history_detail(platform: str, problem_ref: str):
    platform = require_platform(platform)
    p = db.get_solved_problem(platform, problem_ref)
    if not p:
        raise HTTPException(status_code=404, detail="없음")
    return {"code": p.get("code", "")}


@router.get("/api/solved-history")
def get_solved_history(
    q: str = Query(""),
    platform: str = Query(""),
    tier_min: int | None = Query(None),
    tier_max: int | None = Query(None),
    sort: str = Query("date-desc"),
    page: int = Query(1, ge=1),
    per_page: int = Query(20, ge=1),
):
    return db.get_solved_history(q=q, platform=platform, tier_min=tier_min,
                                 tier_max=tier_max, sort=sort, page=page, per_page=per_page)
