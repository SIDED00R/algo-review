import logging

import requests

import db
import clients as api_client
from fastapi import APIRouter, HTTPException
from routes.helpers import upstream_failure
from routes.models import GithubImportRequest
from demo_mode import IS_DEMO, demo_block

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


@router.post("/api/import-github")
def import_from_github(req: GithubImportRequest):
    if IS_DEMO:
        demo_block("GitHub 가져오기는 데모 버전에서 지원되지 않습니다.")
    repo = req.repo

    try:
        problems = api_client.get_baekjoonhub_problems(repo, req.token)
    except requests.exceptions.HTTPError as e:
        status = e.response.status_code if e.response is not None else 502
        if status == 404:
            raise HTTPException(status_code=404, detail="저장소를 찾을 수 없습니다. owner/repo 형식과 철자를 확인하세요.")
        if status == 401:
            raise HTTPException(status_code=401, detail="GitHub 토큰이 유효하지 않습니다.")
        raise HTTPException(status_code=502, detail=f"GitHub API 오류 ({type(e).__name__})") from None
    except ValueError as e:
        # clients.github 가 직접 만든 사용자용 안내다 — 특히 "저장소 트리가 잘렸습니다"
        # 는 대처법을 담고 있고, 상류 **장애**가 아니라 요청 대상의 한도 초과다.
        # upstream_failure 로 삼키면 502 + 타입명만 남아 원인도 대처법도 알 수 없고,
        # 502 가 유도하는 "잠시 후 재시도" 는 저장소가 작아지기 전엔 영원히 실패한다.
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise upstream_failure("GitHub API 오류", e)

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
            except Exception as e:
                logger.warning("파일 내용 다운로드 실패 (problem_id=%s, path=%s): %s", problem_id, p["path"], e)
                failed.append(problem_id)
                continue

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
