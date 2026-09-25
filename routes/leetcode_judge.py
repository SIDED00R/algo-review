"""LeetCode 채점기 라우트 — 뷰어의 '예제 실행'(interpret_solution)과 'LeetCode 에 제출'(submit).

둘 다 서버에 저장된 계정 하나(LEETCODE_SESSION)로 호출한다 — 개인용 앱이다. 사용자 인증이 없는
공개 엔드포인트라 프로세스 전역 분당 상한을 둔다(익명 남용으로 계정이 제한되는 것을 막는 몫).
"""
import logging
import threading
import time

import clients as api_client
from clients import ProblemNotFound, UpstreamUnavailable
from clients.leetcode import normalize_leetcode_problem_ref
from clients.leetcode_judge import (JUDGE_LANGUAGES, LeetCodeRateLimited, LeetCodeSessionError, run_examples,
                                    submit_solution)
from fastapi import APIRouter, HTTPException
from demo_mode import IS_DEMO, demo_block
from routes.models import LeetcodeRunRequest, LeetcodeSubmitRequest

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

_GLOBAL_LIMIT_PER_MINUTE = 20
_rate_lock = threading.Lock()
_recent_calls: list[float] = []


def _enforce_rate_limit() -> None:
    now = time.time()
    with _rate_lock:
        _recent_calls[:] = [t for t in _recent_calls if t > now - 60]
        if len(_recent_calls) >= _GLOBAL_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=429, detail="LeetCode 호출이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
        _recent_calls.append(now)


def _resolve(problem_ref: str, language: str) -> tuple[str, str]:
    """(slug, question_id). 형식 오류 400, 없는 문제 404, 채점기가 모르는 언어 400."""
    if language not in JUDGE_LANGUAGES:
        raise HTTPException(status_code=400, detail=f"LeetCode 채점기가 지원하지 않는 언어: {language}")
    try:
        slug = normalize_leetcode_problem_ref(problem_ref)
        raw = api_client.scrape_lc_problem(slug)
    except ProblemNotFound as e:
        raise HTTPException(status_code=404, detail=str(e)) from None
    except UpstreamUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    if not raw.get("question_id"):
        raise HTTPException(status_code=502, detail="LeetCode 문제의 내부 번호를 받지 못했습니다.")
    return slug, raw["question_id"]


def _call_judge(action: str, fn, *args) -> dict:
    try:
        return fn(*args)
    except LeetCodeSessionError as e:
        raise HTTPException(status_code=401, detail=str(e)) from None
    except LeetCodeRateLimited as e:
        raise HTTPException(status_code=429, detail=str(e)) from None
    except UpstreamUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except Exception as e:
        # 쿠키를 실은 호출 경로다 — 예외 원문을 노출하지 않고 타입명만 노출한다.
        logger.warning("LeetCode %s 실패: %s", action, type(e).__name__)
        raise HTTPException(status_code=502, detail=f"LeetCode {action} 실패 ({type(e).__name__})") from None


@router.post("/api/leetcode/run")
def run_leetcode_examples(req: LeetcodeRunRequest):
    if IS_DEMO:
        demo_block("LeetCode 예제 실행은 데모 버전에서 지원되지 않습니다.")
    if not req.cases:
        raise HTTPException(status_code=400, detail="실행할 예제가 없습니다.")
    _enforce_rate_limit()
    slug, question_id = _resolve(req.problem_ref, req.language)
    return _call_judge("예제 실행", run_examples, slug, question_id, req.language, req.code, req.cases)


@router.post("/api/leetcode/submit")
def submit_to_leetcode(req: LeetcodeSubmitRequest):
    if IS_DEMO:
        demo_block("LeetCode 제출은 데모 버전에서 지원되지 않습니다.")
    _enforce_rate_limit()
    slug, question_id = _resolve(req.problem_ref, req.language)
    return _call_judge("제출", submit_solution, slug, question_id, req.language, req.code)
