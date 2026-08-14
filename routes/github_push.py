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
    folder = push_review_bundle(
        github_repo, github_token,
        platform=req.platform, problem_ref=req.problem_ref, title=req.title,
        tier_name=req.tier_name, tags=req.tags, language=req.language, code=req.code,
        url=req.url, review=reviews[0] if reviews else None,
        description=req.description, input_desc=req.input_desc, output_desc=req.output_desc,
    )
    return {"pushed": True, "repo": github_repo, "path": folder}
