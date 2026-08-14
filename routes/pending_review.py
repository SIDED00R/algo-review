"""LLM 리뷰 없이 풀이를 GitHub 에 올리고 '리뷰 대기'로 기록한다.

토큰이 없어 /api/review 가 실패할 때 쓰는 경로다. 나중에 /api/rereview 가 이 기록을 채우고
저장소 문서를 갱신한다.
"""
import db
from fastapi import APIRouter, HTTPException
from routes.helpers import push_review_bundle, require_github_target
from routes.models import ReviewRequest
from routes.problem_resolve import resolve_problem_info
from demo_mode import IS_DEMO, DEMO_PROBLEM_INFO

router = APIRouter()

_PENDING_REVIEW = {"efficiency": db.PENDING_EFFICIENCY}


@router.post("/api/review/pending")
def push_without_review(req: ReviewRequest):
    if not req.code.strip():
        raise HTTPException(status_code=400, detail="코드가 비어있습니다.")

    if IS_DEMO:
        # 데모는 외부 API·GitHub 를 치지 않는다 — mock 문제 정보로 기록만 남긴다.
        info = DEMO_PROBLEM_INFO
        github_repo, folder = "demo_user/algorithm-solutions", f"demo/{info['problem_ref']}"
    else:
        info = resolve_problem_info(req.platform, req.problem_id, req.problem_ref)
        github_repo, github_token = require_github_target()
        folder = push_review_bundle(
            github_repo, github_token,
            platform=info["platform"], problem_ref=info["problem_ref"], title=info["title"],
            tier_name=info["tier_name"], tags=info["tags"], language=req.language,
            code=req.code, url=info.get("url", ""), review=_PENDING_REVIEW,
            description=(req.problem_statement or "").strip(),
        )

    # push 성공 후에만 기록한다 — 저장소에 없는 유령 기록이 남지 않는다.
    db.save_review(
        problem_id=info["id"], title=info["title"], tier=info["tier"],
        tier_name=info["tier_name"], tags=info["tags"], code=req.code,
        feedback="", efficiency=db.PENDING_EFFICIENCY,
        strengths=[], weaknesses=[], platform=info["platform"],
        problem_ref=info["problem_ref"], language=req.language,
    )
    return {"pushed": True, "repo": github_repo, "path": folder}
