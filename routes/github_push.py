import db
from fastapi import APIRouter
from routes.models import PushReviewRequest
from routes.helpers import (push_review_bundle, require_github_target, require_language,
                            require_problem_ref)
from demo_mode import IS_DEMO

router = APIRouter()


@router.post("/api/push-review")
def push_review_to_github(req: PushReviewRequest):
    language = require_language(req.language)
    # 조회와 push 가 **같은 ref** 를 써야 한다. 정규화 전 값으로 조회하면 `4/A` 가 0건을
    # 받고, push 는 정규화된 `4A` 경로로 나가 그 문제의 README 를 리뷰 섹션 없이 덮어쓴다.
    problem_ref = require_problem_ref(req.platform, req.problem_ref)
    if IS_DEMO:
        return {"pushed": True, "repo": "demo_user/algorithm-solutions",
                "path": f"demo/{problem_ref}"}
    github_repo, github_token = require_github_target()

    # 저장된 최신 리뷰를 README 에 함께 싣는다 — 리뷰 직후 push 이므로 방금 결과가 최신 행이다.
    reviews = db.get_reviews_by_problem(req.platform, problem_ref)
    latest = reviews[0] if reviews else None
    # 요청에 본문이 없으면 저장된 본문으로 대신한다 — 빈 섹션으로 README 를 재생성해
    # 기존 문제 설명을 지우지 않도록. 회차 중 본문이 있는 가장 최근 것을 쓴다.
    description = req.description or db.get_stored_problem_statement(req.platform, problem_ref)
    folder = push_review_bundle(
        github_repo, github_token,
        platform=req.platform, problem_ref=problem_ref, title=req.title,
        tier_name=req.tier_name, tags=req.tags, language=language, code=req.code,
        url=req.url, review=latest,
        description=description, input_desc=req.input_desc, output_desc=req.output_desc,
    )
    return {"pushed": True, "repo": github_repo, "path": folder}
