"""백준 문제 뷰어 — 문제 페이지의 본문·제한·예제를 CF 뷰어와 같은 모양으로 돌려준다.

본문은 한국어 원문이라 번역하지 않는다. `statement_sections_html` 은 화면이 정화해 그리는 HTML 이고,
`statement_sections_ko` 는 같은 섹션의 텍스트판이다(질문 칸 문맥·GitHub README 본문). 예제는 이 앱의
실행기(stdin/stdout)로 채점한다.
"""
import asyncio

import clients as api_client
from fastapi import APIRouter, HTTPException
from routes import problem_cache
from routes.helpers import require_problem_ref, upstream_failure
from demo_mode import IS_DEMO, DEMO_BOJ_PROBLEM

router = APIRouter()


@router.get("/api/problem/boj/{problem_id}")
async def get_boj_problem(problem_id: str):
    if IS_DEMO:
        return DEMO_BOJ_PROBLEM

    number = int(require_problem_ref("boj", problem_id))
    cache_key = f"boj:{number}"
    return await problem_cache.run_deduplicated(cache_key, lambda: _scrape(cache_key, number))


async def _scrape(cache_key: str, problem_id: int) -> dict:
    try:
        # 동기 HTTP 호출(최대 10초)이라 이벤트 루프를 막지 않게 스레드로 뺀다.
        raw = await asyncio.to_thread(api_client.scrape_boj_problem, problem_id)
    except api_client.ProblemNotFound as e:
        # 없는 문제다 — 502 는 절대 성공하지 않을 재시도를 유도한다.
        raise HTTPException(status_code=404, detail=str(e)) from None
    except Exception as e:
        raise upstream_failure("백준 문제 페이지 로딩 실패", e)

    result = {
        "problem_id": raw["problem_id"],
        "title": raw["title"],
        "time_limit": raw["time_limit"],
        "memory_limit": raw["memory_limit"],
        "statement_sections_html": raw["sections_html"],
        "statement_sections_ko": raw["sections_text"],
        "samples": raw["samples"],
        "url": raw["url"],
    }
    # 번역이 없어 실패 재시도가 필요 없다 — 성공 결과는 만료 없이 둔다.
    problem_cache.cache_set(cache_key, result, True)
    return result
