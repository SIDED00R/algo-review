"""'리뷰 대기'로 올린 풀이를 나중에 AI 리뷰로 채우고 저장소 문서를 갱신한다."""
import logging

import analyzer
import db
from config import settings
from fastapi import APIRouter, HTTPException
from routes.helpers import (merged_github_target, push_review_bundle, require_reviewable_code,
                            require_platform, upstream_failure)
from routes.problem_resolve import resolve_statement
from demo_mode import IS_DEMO, DEMO_REVIEW_RESULT

router = APIRouter()
logger = logging.getLogger("uvicorn.error")


def _run_review(platform: str, review: dict) -> dict:
    """대기 행의 코드로 AI 리뷰를 돌린다. 문제 메타는 저장된 행에 이미 있어 재조회하지 않는다."""
    if IS_DEMO:
        return DEMO_REVIEW_RESULT
    if not settings.openai_api_key:
        # 설정 누락은 서버 문제다 — review/report/solved 와 같은 500 으로 맞춘다.
        raise HTTPException(status_code=500,
                            detail="OPENAI_API_KEY가 설정되지 않았습니다. LLM을 쓸 수 있을 때 다시 시도해주세요.")

    problem_info = {
        "id": review["problem_id"], "platform": platform,
        "problem_ref": review["problem_ref"], "title": review["title"],
        "tier": review["tier"], "tier_name": review["tier_name"], "tags": review["tags"],
    }
    # 저장된 본문(없으면 최신 회차 것)을 넘긴다 — 아래 _repush_bundle 도 같은 값을 쓴다.
    statement = resolve_statement(
        platform, problem_info,
        db.get_stored_problem_statement(platform, review["problem_ref"]))
    # 상한 도입 이전에 저장된 행이 있을 수 있다 — 저장 시점 검증만 믿지 않고 여기서도 본다.
    require_reviewable_code(review["code"])
    try:
        return analyzer.analyze_code(problem_info, statement, review["code"])
    except ValueError as e:
        # analyzer 가 직접 만든 사용자용 안내는 그대로 보여준다.
        raise HTTPException(status_code=502, detail=str(e))
    except Exception as e:
        raise upstream_failure("코드 분석 실패", e)


def _repush_bundle(platform: str, problem_ref: str, review: dict) -> tuple[bool, str | None]:
    """리뷰 내용을 담은 README + 코드를 다시 올린다. 실패해도 리뷰 저장은 유지하고 이유만 돌려준다."""
    if IS_DEMO:
        return True, None
    github_repo, github_token = merged_github_target()
    if not github_repo or not github_token:
        return False, "GitHub 연결·저장소 선택이 필요합니다. 리뷰는 저장되었습니다."
    if not review.get("language"):
        # language 가 빈 기록이다 — 확장자를 모르면 엉뚱한 파일을 새로 만들게 된다.
        return False, ("저장된 언어 정보가 없어 파일명을 재현할 수 없습니다. "
                       "리뷰 탭에서 언어를 선택해 다시 올려주세요. 리뷰는 저장되었습니다.")

    try:
        push_review_bundle(
            github_repo, github_token,
            platform=platform, problem_ref=problem_ref, title=review["title"],
            tier_name=review["tier_name"], tags=review["tags"], language=review["language"],
            code=review["code"], review=review, submitted_at=review.get("created_at", ""),
            # 저장된 본문이 있으면 그걸 쓴다 — 없으면 push_review_bundle 이 스크래핑하고, BOJ 는
            # 빈 섹션이 돌아와 이미 올라간 문제 설명을 지운다.
            description=review.get("problem_statement") or db.get_stored_problem_statement(platform, problem_ref),
        )
    except HTTPException as e:
        return False, f"GitHub 업로드 실패: {e.detail} 리뷰는 저장되었습니다."
    except Exception as e:
        # 본문 수집·URL 정규화 등에서 새는 예외까지 잡는다 — 리뷰는 이미 저장돼 있으므로
        # 500 으로 터뜨리면 "리뷰는 유지한다"는 계약이 깨진다.
        logger.warning("재업로드 실패 (%s/%s): %s", platform, problem_ref, e)
        # 타입명만 싣는다 — 하류에 requests 호출이 하나 늘면 예외 메시지에 요청 URL 전문이
        # 들어오고, 그것이 그대로 응답이 된다(routes/helpers.py upstream_failure 와 같은 정책).
        return False, f"GitHub 업로드 실패({type(e).__name__}). 리뷰는 저장되었습니다."
    return True, None


@router.post("/api/rereview/{platform}/{problem_ref}")
def rereview_problem(platform: str, problem_ref: str):
    """문제의 최신 회차가 대기 행이면 AI 리뷰로 채운 뒤, 어느 경우든 저장소 문서를 다시 올린다.

    이미 리뷰된 행이면 LLM 을 호출하지 않는다 — push 만 실패했을 때 프론트의
    'GitHub 문서 다시 올리기' 버튼이 이 경로로 토큰 없이 업로드만 재시도한다.
    """
    platform = require_platform(platform)

    reviews = db.get_reviews_by_problem(platform, problem_ref)
    if not reviews:
        raise HTTPException(status_code=404, detail="리뷰 기록을 찾을 수 없습니다.")
    latest = reviews[0]

    reviewed = False
    if latest["efficiency"] == db.PENDING_EFFICIENCY:
        result = _run_review(platform, latest)
        # 리뷰한 그 회차에 쓴다 — LLM 이 도는 사이 대기 회차가 하나 더 쌓일 수 있어,
        # '최신 대기 행' 에 쓰면 리뷰한 적 없는 코드에 결과가 붙는다.
        if not db.update_pending_review(platform, problem_ref, result,
                                        review_id=latest["id"]):
            raise HTTPException(
                status_code=409,
                detail="이 회차가 그 사이에 채워졌거나 사라졌습니다. 목록을 다시 불러와 주세요.")
        reviewed = True
        # 방금 채운 회차를 다시 읽는다 — 그 사이 더 최신 회차가 생겼을 수 있어 [0] 을
        # 집으면 README 에 다른 회차의 코드가 올라간다.
        latest = next(r for r in db.get_reviews_by_problem(platform, problem_ref)
                      if r["id"] == latest["id"])

    pushed, detail = _repush_bundle(platform, problem_ref, latest)
    # 갱신된 리뷰 내용은 프론트가 기록 조회로 다시 읽는다 — 코드 전문을 응답에 싣지 않는다.
    return {"reviewed": reviewed, "pushed": pushed, "detail": detail}
