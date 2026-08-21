import db
import clients as api_client
from routes.models import ReviewResponse


def save_and_build_response(problem_info: dict, code: str, result: dict,
                            language: str = "",
                            problem_statement: str = "") -> ReviewResponse:
    """리뷰 결과로 응답을 조립·검증한 뒤 저장한다. review/solved 라우터 공용.

    검증을 저장보다 먼저 해야 한다 — 순서가 반대면 LLM 응답이 스키마와 어긋나 검증이 실패했을 때
    이미 저장된 행이 남아 재시도할 때마다 제출 회차만 늘어난다.
    complexity 는 저장·응답 양쪽에서 기본값을 ""로 통일한다 — result.get(key, default)는 LLM 이
    "complexity": null 을 준 경우(키는 있고 값이 None) default 를 적용하지 않으므로 or 로 처리한다.
    """
    complexity = result.get("complexity") or ""
    response = ReviewResponse(
        problem_id=problem_info["id"],
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
        problem_url=api_client.get_problem_url(problem_info["platform"], problem_info["problem_ref"]),
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        efficiency=result["efficiency"],
        complexity=complexity,
        better_algorithm=result.get("better_algorithm"),
        feedback=result.get("feedback", ""),
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
    )

    db.save_review(
        problem_id=problem_info["id"],
        title=problem_info["title"],
        tier=problem_info["tier"],
        tier_name=problem_info["tier_name"],
        tags=problem_info["tags"],
        code=code,
        feedback=result.get("feedback", ""),
        efficiency=result["efficiency"],
        complexity=complexity,
        better_algorithm=result.get("better_algorithm") or "",
        strengths=result.get("strengths", []),
        weaknesses=result.get("weaknesses", []),
        platform=problem_info["platform"],
        problem_ref=problem_info["problem_ref"],
        language=language,
        problem_statement=problem_statement,
    )
    return response
