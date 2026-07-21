import time
import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from config import settings
from routes.models import CodeforcesImportRequest
from routes.helpers import build_readme, push_solution, build_solution_target, merged_github_target
from demo_mode import IS_DEMO, demo_block

router = APIRouter()


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
        time.sleep(2.1)
        submissions = api_client.get_codeforces_user_submissions(
            handle,
            count=req.count,
            api_key=api_key,
            api_secret=api_secret,
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Codeforces 기록 조회 실패: {e}")

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
            language=sub.get("language", ""),
            platform="codeforces",
            problem_ref=sub["problem_ref"],
        )
        if github_push_enabled and sub.get("code"):
            ext = api_client._get_file_extension(sub.get("language", ""))
            ref = sub["problem_ref"]
            folder, msg = build_solution_target("codeforces", ref, sub["title"])
            cf_url = sub.get("problem_url", api_client.get_problem_url("codeforces", ref))
            readme = build_readme(ref, sub["title"],
                                  sub.get("tier_name", ""), sub.get("tags", []),
                                  sub.get("language", ""), cf_url)
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
