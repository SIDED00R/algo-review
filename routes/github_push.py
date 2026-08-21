import db
from fastapi import APIRouter
from routes.models import PushReviewRequest
from routes.helpers import push_review_bundle, require_github_target
from demo_mode import IS_DEMO

router = APIRouter()


@router.post("/api/push-review")
def push_review_to_github(req: PushReviewRequest):
    if IS_DEMO:
        return {"pushed": True, "repo": "demo_user/algorithm-solutions",
                "path": f"demo/{req.problem_ref}"}
    github_repo, github_token = require_github_target()

    # 저장된 최신 리뷰를 README 에 함께 싣는다 — 리뷰 직후 push 이므로 방금 결과가 최신 행이다.
    reviews = db.get_reviews_by_problem(req.platform, req.problem_ref)
    latest = reviews[0] if reviews else None
    # 요청에 본문이 없으면 저장된 본문으로 대신한다. 스크래핑이 죽은 플랫폼(BOJ)에서
    # 빈 섹션으로 README 를 재생성해 기존 문제 설명을 지우는 것을 막는다.
    description = req.description or (latest or {}).get("problem_statement", "")
    folder = push_review_bundle(
        github_repo, github_token,
        platform=req.platform, problem_ref=req.problem_ref, title=req.title,
        tier_name=req.tier_name, tags=req.tags, language=req.language, code=req.code,
        url=req.url, review=latest,
        description=description, input_desc=req.input_desc, output_desc=req.output_desc,
    )
    return {"pushed": True, "repo": github_repo, "path": folder}
