"""LeetCode 문제 뷰어 — 본문 HTML 을 받아 한국어로 번역해 돌려준다.

예제 실행은 없다. LeetCode 문제는 함수 시그니처 기반이고 Database 문제는 SQL 이라
stdin/stdout 실행기로 채점할 수 없다.
"""
import asyncio

import clients as api_client
from clients.leetcode import normalize_leetcode_problem_ref
from fastapi import APIRouter, HTTPException
from routes import problem_cache
from routes.helpers import upstream_failure
from demo_mode import IS_DEMO, DEMO_LC_PROBLEM
from statement_translator import MAX_TRANSLATE_LENGTH, translate_statement

router = APIRouter()


@router.get("/api/problem/lc/{problem_ref}")
async def get_lc_problem(problem_ref: str):
    if IS_DEMO:
        return DEMO_LC_PROBLEM

    try:
        slug = normalize_leetcode_problem_ref(problem_ref)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    cache_key = f"lc:{slug}"
    return await problem_cache.run_deduplicated(cache_key, lambda: _fetch_and_translate(cache_key, slug))


async def _fetch_and_translate(cache_key: str, slug: str) -> dict:
    try:
        # 동기 HTTP 호출이라 이벤트 루프를 막지 않게 스레드로 뺀다 — 아래 번역과 같은 이유.
        raw = await asyncio.to_thread(api_client.scrape_lc_problem, slug)
    except api_client.ProblemNotFound as e:
        # 형식은 맞지만 없는 문제다 — 502 는 절대 성공하지 않을 재시도를 유도한다.
        raise HTTPException(status_code=404, detail=str(e)) from None
    except api_client.UpstreamUnavailable as e:
        raise HTTPException(status_code=502, detail=str(e)) from None
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from None
    except Exception as e:
        raise upstream_failure("LeetCode 문제 로딩 실패", e)

    html = raw["content_html"]
    content_ko, translated = html, False
    if html and len(html) <= MAX_TRANSLATE_LENGTH:
        # 유료 호출이다 — 상한을 넘으면 원문을 그대로 보여준다(번역 실패와 같은 처리).
        try:
            content_ko = await asyncio.to_thread(
                translate_statement, html, raw["title"], source="LeetCode", html=True)
            translated = True
        except Exception:
            pass

    result = {
        "title": raw["title"],
        "problem_id": raw["problem_id"],
        "difficulty": raw["difficulty"],
        "tier": raw["tier"],
        "category": raw["category"],
        "is_paid_only": raw["is_paid_only"],
        "tags": raw["tags"],
        "content_html_ko": content_ko,
        "url": raw["url"],
        "translated": translated,
    }
    # 번역 성공 시 영구 캐시, 실패 시 60초 뒤 재시도. 본문이 없는 유료 문제는 번역할 것이 없어 영구 캐시한다.
    problem_cache.cache_set(cache_key, result, translated or not html)
    return result
