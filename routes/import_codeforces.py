import logging
import time
import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from config import settings
from clients import UpstreamUnavailable
from routes.models import CodeforcesImportRequest
from routes.helpers import build_readme, push_solution, build_solution_target, merged_github_target
from demo_mode import IS_DEMO, demo_block

logger = logging.getLogger("uvicorn.error")
router = APIRouter()

# CF API 는 2초에 1회를 넘기면 429 를 준다 — 여유를 두고 쉰다.
_CF_RATE_LIMIT_SEC = 2.1


@router.post("/api/import-codeforces")
def import_codeforces_history(req: CodeforcesImportRequest):
    if IS_DEMO:
        demo_block("Codeforces 가져오기는 데모 버전에서 지원되지 않습니다.")
    handle = req.handle

    api_key = (req.api_key or settings.codeforces_api_key or "").strip() or None
    api_secret = (req.api_secret or settings.codeforces_api_secret or "").strip() or None
    if bool(api_key) != bool(api_secret):
        raise HTTPException(status_code=400, detail="Codeforces API Key와 Secret은 둘 다 입력하거나 둘 다 비워두세요.")

    try:
        user = api_client.get_codeforces_user_info(handle)
        time.sleep(_CF_RATE_LIMIT_SEC)
        submissions = api_client.get_codeforces_user_submissions(
            handle,
            count=req.count,
            api_key=api_key,
            api_secret=api_secret,
        )
    except UpstreamUnavailable as e:
        # 상류 장애다 — 400 으로 주면 사용자가 자기 입력을 고치려 한다.
        raise HTTPException(status_code=502, detail=str(e))
    except ValueError as e:
        # ValueError 는 clients.codeforces 가 직접 만든 안전한 메시지만 담는다.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        # 서명 호출 경로다 — 예외 원문에 apiKey·apiSig 가 실린 URL 이 들어올 수 있으므로
        # 타입명만 노출한다. 세부 내용은 서버 로그에서만 본다.
        logger.exception("Codeforces 기록 조회 실패")
        raise HTTPException(status_code=502,
                            detail=f"Codeforces 기록 조회 실패 ({type(e).__name__})") from None

    existing_keys = db.get_solved_problem_keys()
    new_subs = [s for s in submissions if ("codeforces", s["problem_ref"]) not in existing_keys]
    skipped = len(submissions) - len(new_subs)

    github_repo, github_token = merged_github_target(req.github_repo or "", req.github_token or "")
    github_push_enabled = bool(github_repo and github_token)
    github_pushed = 0

    for sub in new_subs:
        db.save_solved_problem(
            problem_id=0,
            title=sub["title"],
            tier=0,
            tier_name=sub["tier_name"],
            tags=sub["tags"],
            code=sub["code"],
            language=sub["language"],
            platform="codeforces",
            problem_ref=sub["problem_ref"],
        )
        if github_push_enabled and sub.get("code"):
            # get_codeforces_user_submissions 가 아래 키를 전부 채운다 — 계약을 믿고 직접 인덱싱한다.
            ext = api_client.get_file_extension(sub["language"])
            ref = sub["problem_ref"]
            folder, msg = build_solution_target("codeforces", ref, sub["title"])
            readme = build_readme(ref, sub["title"], sub["tier_name"], sub["tags"],
                                  sub["language"], sub["problem_url"])
            if push_solution(github_repo, github_token, folder,
                             ref, ext, sub["code"], readme, msg):
                github_pushed += 1

    return {
        "handle": user.get("handle", handle),
        "total_found": len(submissions),
        "imported": len(new_subs),
        "skipped": skipped,
        "has_source": any(bool(s.get("code")) for s in submissions),
        "github_pushed": github_pushed,
        "github_repo": github_repo or "",
    }
