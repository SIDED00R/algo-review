"""문제 식별자 → 문제 메타/본문 해석. 리뷰·리뷰 대기 등록·재리뷰 라우터가 공유한다."""
import clients as api_client
import db
from fastapi import HTTPException


def resolve_problem_info(platform: str, problem_id: int | None, problem_ref: str | None) -> dict:
    """플랫폼별 문제 메타(제목·티어·태그)를 반환한다. LLM 을 쓰지 않는다."""
    if platform == "codeforces":
        if not (problem_ref or "").strip():
            raise HTTPException(status_code=400, detail="Codeforces 문제 번호를 입력하세요. 예: 4A 또는 4/A")
        try:
            return api_client.get_codeforces_problem_info(problem_ref.strip())
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Codeforces 문제 조회 실패: {e}")

    if problem_id is None:
        raise HTTPException(status_code=400, detail="백준 문제 번호를 입력하세요.")

    info = db.get_cached_problem_info(problem_id)
    if not info:
        try:
            info = api_client.get_problem_info(problem_id)
        except Exception:
            info = {
                "id": problem_id,
                "platform": "boj",
                "problem_ref": str(problem_id),
                "title": f"문제 {problem_id}",
                "tier": 0,
                "tier_name": "Unrated",
                "tags": [],
            }
    info["platform"] = "boj"
    info["problem_ref"] = str(problem_id)
    return info


# 본문 수집 함수들은 예외를 던지지 않고 실패 문자열을 반환한다. 그걸 그대로 LLM 에 넘기면
# 프롬프트의 문제 설명 자리에 에러 메시지가 박힌다 — acmicpc.net 종료 이후 BOJ 리뷰가
# 실제로 이 상태였다. 빈 본문을 주는 편이 낫다(analyzer 가 제목·티어·태그·코드로 분석한다).
_SCRAPE_FAILURE_PREFIXES = (
    "크롤링 실패",
    "문제 설명을 가져올 수 없습니다",
    "문제 설명 자동 수집에 실패했습니다",
)


def is_scrape_failure(text: str) -> bool:
    """수집 함수가 본문 대신 돌려준 실패 문자열인지 판정한다."""
    stripped = (text or "").strip()
    return not stripped or stripped.startswith(_SCRAPE_FAILURE_PREFIXES)


def resolve_statement(platform: str, info: dict, custom_statement: str | None = None) -> str:
    """LLM 리뷰에 넣을 문제 본문. 사용자가 붙여 넣은(또는 저장된) 본문이 있으면 그것을 쓴다."""
    custom = (custom_statement or "").strip()
    if custom:
        return custom
    if platform == "codeforces":
        scraped = api_client.get_codeforces_problem_statement(info["problem_ref"])
    else:
        scraped = api_client.get_problem_statement(int(info["problem_ref"]))
    return "" if is_scrape_failure(scraped) else scraped
