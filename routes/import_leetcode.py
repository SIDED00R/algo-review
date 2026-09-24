import logging
import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from config import settings
from clients import UpstreamUnavailable
from routes.models import LeetcodeImportRequest
from routes.helpers import build_readme, push_solution, build_solution_target, merged_github_target
from demo_mode import IS_DEMO, demo_block

logger = logging.getLogger("uvicorn.error")
router = APIRouter()


@router.post("/api/import-leetcode")
def import_leetcode_history(req: LeetcodeImportRequest):
    if IS_DEMO:
        demo_block("LeetCode 가져오기는 데모 버전에서 지원되지 않습니다.")

    # 세션 쿠키가 있으면 내 AC 제출 코드까지, 없으면 공개 API 의 최근 AC 목록만(코드 없음).
    session = (req.session or settings.leetcode_session or "").strip() or None

    try:
        submissions = api_client.get_leetcode_user_submissions(req.username, count=req.count, session=session)
    except UpstreamUnavailable as e:
        # 상류 장애다 — 400 으로 주면 사용자가 자기 입력을 고치려 한다.
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        # ValueError 는 clients.leetcode 가 직접 만든 안전한 메시지만 담는다.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 쿠키를 실은 호출 경로다 — 예외 원문을 노출하지 않고 타입명만 노출한다.
        logger.exception("LeetCode 기록 조회 실패")
        raise HTTPException(status_code=502,
                            detail=f"LeetCode 기록 조회 실패 ({type(e).__name__})") from None

    existing_keys = db.get_solved_problem_keys()
    new_subs = [s for s in submissions if ("leetcode", s["problem_ref"]) not in existing_keys]
    skipped = len(submissions) - len(new_subs)

    github_repo, github_token = merged_github_target(req.github_repo or "", req.github_token or "")
    github_push_enabled = bool(github_repo and github_token)
    github_pushed = 0

    for sub in new_subs:
        db.save_solved_problem(
            problem_id=sub["problem_id"],
            title=sub["title"],
            tier=sub["tier"],
            tier_name=sub["tier_name"],
            tags=sub["tags"],
            code=sub["code"],
            language=sub["language"],
            platform="leetcode",
            problem_ref=sub["problem_ref"],
        )
        if github_push_enabled and sub.get("code"):
            ext = api_client.get_file_extension(sub["language"])
            ref = sub["problem_ref"]
            folder, msg = build_solution_target("leetcode", ref, sub["title"], sub["tier_name"])
            readme = build_readme(ref, sub["title"], sub["tier_name"], sub["tags"],
                                  sub["language"], sub["problem_url"])
            if push_solution(github_repo, github_token, folder,
                             ref, ext, sub["code"], readme, msg):
                github_pushed += 1

    return {
        "username": req.username,
        "total_found": len(submissions),
        "imported": len(new_subs),
        "skipped": skipped,
        "has_source": any(bool(s.get("code")) for s in submissions),
        "github_pushed": github_pushed,
        "github_repo": github_repo or "",
    }
