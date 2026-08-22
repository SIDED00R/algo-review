"""문제 식별자 → 문제 메타/본문 해석. 리뷰·리뷰 대기 등록·재리뷰 라우터가 공유한다."""
import clients as api_client
import db
from fastapi import HTTPException

# solved.ac 조회가 실패했을 때 쓰는 자리표시 제목. BOJ 문제의 실제 제목이 이 형태가 될 수
# 없으므로, 나중에 그 행을 캐시로 읽었을 때 "아직 해석되지 않은 메타" 임을 알아볼 수 있다.
_UNRESOLVED_TITLE = "문제 {}"


def _unresolved_problem_info(problem_id: int) -> dict:
    """solved.ac 조회 실패 시의 자리표시 메타.

    리뷰 자체는 진행돼야 한다 — 코드는 이미 받았고 analyzer 는 제목·티어 없이도 분석한다.
    다만 이 값이 reviews 행으로 저장되면 그 행이 다음 조회의 캐시가 되므로
    (`db.get_cached_problem_info` 는 가장 최근 리뷰 행을 캐시로 쓴다), 자리표시임을
    알아볼 수 있어야 한다.
    """
    return {
        "id": problem_id,
        "platform": "boj",
        "problem_ref": str(problem_id),
        "title": _UNRESOLVED_TITLE.format(problem_id),
        "tier": 0,
        "tier_name": "Unrated",
        "tags": [],
    }


def is_unresolved_problem_info(info: dict, problem_id: int) -> bool:
    """자리표시 메타인지 — 실제 문제 메타와 구분한다.

    티어 0 + 태그 없음만으로는 판정할 수 없다. solved.ac 에 실제로 Unrated 로 등록된
    문제가 그 형태이고, 그것까지 자리표시로 보면 리뷰할 때마다 조회를 다시 하게 된다.
    """
    return (info.get("title") == _UNRESOLVED_TITLE.format(problem_id)
            and not info.get("tier") and not info.get("tags"))


def resolve_problem_info(platform: str, problem_id: int | None, problem_ref: str | None) -> dict:
    """플랫폼별 문제 메타(제목·티어·태그)를 반환한다. LLM 을 쓰지 않는다."""
    if platform == "codeforces":
        if not (problem_ref or "").strip():
            raise HTTPException(status_code=400, detail="Codeforces 문제 번호를 입력하세요. 예: 4A 또는 4/A")
        try:
            return api_client.get_codeforces_problem_info(problem_ref.strip())
        except api_client.UpstreamUnavailable as e:
            # 상류 장애다 — 400 으로 주면 사용자가 자기 입력을 고치려 한다.
            raise HTTPException(status_code=502, detail=str(e))
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=502,
                                detail=f"Codeforces 문제 조회 실패 ({type(e).__name__})") from None

    if problem_id is None:
        raise HTTPException(status_code=400, detail="백준 문제 번호를 입력하세요.")

    def _as_boj(info: dict) -> dict:
        info["platform"] = "boj"
        info["problem_ref"] = str(problem_id)
        return info

    cached = db.get_cached_problem_info(problem_id)
    if cached and not is_unresolved_problem_info(cached, problem_id):
        return _as_boj(cached)

    # 캐시가 없거나 자리표시면 solved.ac 를 다시 시도한다 — 자리표시를 캐시로 인정하면
    # 일시 장애 중 만들어진 메타가 DB 수명 동안 고착된다.
    try:
        info = api_client.get_problem_info(problem_id)
    except Exception:
        return _as_boj(cached or _unresolved_problem_info(problem_id))

    if cached:
        # 자리표시로 저장된 과거 행을 실제 메타로 되살린다 — 집계 기준인 '첫 판정 행' 이
        # 자리표시로 남으면 새 리뷰를 아무리 해도 통계가 회복되지 않는다.
        db.refresh_unresolved_problem_metadata(problem_id, info)
    return _as_boj(info)


# 본문 수집 함수는 예외 대신 실패 문자열을 반환한다 — 그대로 LLM 에 넘기면 프롬프트의
# 문제 설명 자리에 에러 메시지가 박힌다. 빈 본문을 주는 편이 낫다.
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
