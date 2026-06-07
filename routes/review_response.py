import db
import clients as api_client
from routes.models import ReviewResponse


def save_and_build_response(problem_info: dict, code: str, result: dict) -> ReviewResponse:
    """리뷰 결과를 저장하고 ReviewResponse를 생성한다. review/solved 라우터 공용."""
    db.save_review(
        problem_id=problem_info["id"],
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        code=code,
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=result.get("complexity", ""),
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
    )
    return ReviewResponse(
        problem_id=problem_info["id"],
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
        problem_url=api_client.get_problem_url(problem_info["platform"], problem_info["problem_ref"]),
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        efficiency=result["efficiency"],
        complexity=result.get("complexity", "N/A"),
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )
