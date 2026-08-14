"""'리뷰 대기'로 올린 풀이를 나중에 AI 리뷰로 채우고 저장소 문서를 갱신한다."""
import analyzer
import db
from config import settings
from fastapi import APIRouter, HTTPException
from routes.helpers import merged_github_target, push_review_bundle
from routes.problem_resolve import resolve_statement
from demo_mode import IS_DEMO, DEMO_REVIEW_RESULT

router = APIRouter()


def _run_review(platform: str, review: dict) -> dict:
    """대기 행의 코드로 AI 리뷰를 돌린다. 문제 메타는 저장된 행에 이미 있어 재조회하지 않는다."""
    if IS_DEMO:
        return DEMO_REVIEW_RESULT
    if not settings.openai_api_key:
        raise HTTPException(status_code=400,
                            detail="OPENAI_API_KEY가 설정되지 않았습니다. LLM을 쓸 수 있을 때 다시 시도해주세요.")

    problem_info = {
        "id": review["problem_id"], "platform": platform,
        "problem_ref": review["problem_ref"], "title": review["title"],
        "tier": review["tier"], "tier_name": review["tier_name"], "tags": review["tags"],
    }
    statement = resolve_statement(platform, problem_info)
    try:
        return analyzer.analyze_code(problem_info, statement, review["code"])
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"코드 분석 실패: {e}")


def _push_readme(platform: str, problem_ref: str, review: dict) -> tuple[bool, str | None]:
    """리뷰 내용을 담은 README + 코드를 다시 올린다. 실패해도 리뷰 저장은 유지하고 이유만 돌려준다."""
    if IS_DEMO:
        return True, None
    github_repo, github_token = merged_github_target()
    if not github_repo or not github_token:
        return False, "GitHub 연결·저장소 선택이 필요합니다. 리뷰는 저장되었습니다."
    if not review.get("language"):
        return False, "저장된 언어 정보가 없어 파일명을 재현할 수 없습니다. 리뷰는 저장되었습니다."

    try:
        push_review_bundle(
            github_repo, github_token,
            platform=platform, problem_ref=problem_ref, title=review["title"],
            tier_name=review["tier_name"], tags=review["tags"], language=review["language"],
            code=review["code"], review=review,
        )
    except HTTPException as e:
        return False, f"GitHub 업로드 실패: {e.detail} 리뷰는 저장되었습니다."
    return True, None


@router.post("/api/rereview/{platform}/{problem_ref}")
def rereview_problem(platform: str, problem_ref: str):
    """대기 행이면 AI 리뷰로 채운 뒤, 어느 경우든 저장소 문서를 다시 올린다.

    이미 리뷰된 행이면 LLM 을 호출하지 않는다 — push 만 실패했을 때 같은 버튼을 다시 눌러
    토큰을 쓰지 않고 업로드만 재시도할 수 있다.
    """
    platform = platform.strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다.")

    reviews = db.get_reviews_by_problem(platform, problem_ref)
    if not reviews:
        raise HTTPException(status_code=404, detail="리뷰 기록을 찾을 수 없습니다.")
    latest = reviews[0]

    reviewed = False
    if latest["efficiency"] == db.PENDING_EFFICIENCY:
        result = _run_review(platform, latest)
        if not db.update_pending_review(platform, problem_ref, result):
            raise HTTPException(status_code=409, detail="리뷰 대기 기록이 사라졌습니다. 목록을 다시 불러와 주세요.")
        reviewed = True
        latest = db.get_reviews_by_problem(platform, problem_ref)[0]

    pushed, detail = _push_readme(platform, problem_ref, latest)
    # 갱신된 리뷰 내용은 프론트가 기록 조회로 다시 읽는다 — 코드 전문을 응답에 싣지 않는다.
    return {"reviewed": reviewed, "pushed": pushed, "detail": detail}
