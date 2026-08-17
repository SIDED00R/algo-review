import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from routes.models import ImportRequest
from routes.helpers import build_readme, push_solution, build_solution_target, merged_github_target
from demo_mode import IS_DEMO, demo_block

router = APIRouter()


@router.post("/api/import")
def import_history(req: ImportRequest):
    if IS_DEMO:
        demo_block("BOJ 가져오기는 데모 버전에서 지원되지 않습니다.")

    try:
        submissions = api_client.get_user_submissions(req.boj_id, req.max_pages)
    except api_client.BojCrawlError as e:
        raise HTTPException(status_code=502, detail=f"BOJ 제출 목록을 불러오지 못했습니다({e}). 잠시 후 다시 시도해주세요.")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"제출 기록 크롤링 실패: {e}")

    existing_ids = db.get_solved_problem_ids()
    new_subs = [s for s in submissions if s["problem_id"] not in existing_ids]
    skipped = len(submissions) - len(new_subs)
    imported, failed = 0, []

    github_repo, github_token = merged_github_target()
    github_push_enabled = bool(github_repo and github_token)
    github_pushed = 0

    if new_subs:
        new_ids = [s["problem_id"] for s in new_subs]
        info_map = api_client.get_problems_bulk(new_ids)

        for sub in new_subs:
            problem_id = sub["problem_id"]
            info = info_map.get(problem_id)
            if not info:
                failed.append(problem_id)
                continue

            code = ""
            if req.session_cookie:
                code = api_client.get_submission_code(sub["submission_id"], req.session_cookie) or ""

            db.save_solved_problem(
                problem_id=problem_id,
                title=info["title"],
                tier=info["tier"],
                tier_name=info["tier_name"],
                tags=info["tags"],
                code=code,
                language=sub.get("language", ""),
                platform="boj",
                problem_ref=str(problem_id),
            )
            if github_push_enabled and code:
                ext = api_client._get_file_extension(sub.get("language", ""))
                folder, msg = build_solution_target("boj", problem_id, info["title"], info.get("tier_name", ""))
                boj_url = f"https://www.acmicpc.net/problem/{problem_id}"
                readme = build_readme(str(problem_id), info["title"],
                                      info.get("tier_name", ""), info.get("tags", []),
                                      sub.get("language", ""), boj_url)
                if push_solution(github_repo, github_token, folder,
                                 str(problem_id), ext, code, readme, msg):
                    github_pushed += 1
            imported += 1

    return {
        "total_found": len(submissions),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
        "github_pushed": github_pushed,
        "github_repo": github_repo or "",
    }
