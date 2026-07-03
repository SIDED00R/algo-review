import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from routes.models import GithubImportRequest
from demo_mode import IS_DEMO, demo_block

router = APIRouter()


@router.post("/api/import-github")
def import_from_github(req: GithubImportRequest):
    if IS_DEMO:
        demo_block("GitHub 가져오기는 데모 버전에서 지원되지 않습니다.")
    repo = req.repo

    try:
        problems = api_client.get_baekjoonhub_problems(repo, req.token)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"GitHub API 오류: {e}")

    if not problems:
        raise HTTPException(status_code=404, detail="백준 풀이 파일을 찾을 수 없습니다. BaekjoonHub 저장소가 맞는지 확인하세요.")

    existing_ids = db.get_solved_problem_ids()
    new_problems = [p for p in problems if p["problem_id"] not in existing_ids]
    skipped = len(problems) - len(new_problems)
    imported, failed = 0, []

    if new_problems:
        new_ids = [p["problem_id"] for p in new_problems]
        info_map = api_client.get_problems_bulk(new_ids)

        for p in new_problems:
            problem_id = p["problem_id"]
            info = info_map.get(problem_id)
            if not info:
                failed.append(problem_id)
                continue

            code = ""
            try:
                code = api_client.get_raw_github_content(repo, p["path"], req.token)
            except Exception:
                pass

            db.save_solved_problem(
                problem_id=problem_id,
                title=info["title"],
                tier=info["tier"],
                tier_name=info["tier_name"],
                tags=info["tags"],
                code=code,
                language=p.get("language", ""),
                platform="boj",
                problem_ref=str(problem_id),
            )
            imported += 1

    return {
        "total_found": len(problems),
        "imported": imported,
        "skipped": skipped,
        "failed": failed,
    }
