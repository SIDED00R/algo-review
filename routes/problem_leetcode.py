"""LeetCode 문제 뷰어 — 본문 HTML 을 받아 한국어로 번역해 돌려준다.

예제 실행·제출은 LeetCode 채점기가 한다(`routes/leetcode_judge.py`). 응답의 `samples` 는 공식 예제의
입력만 담고(`{"input": ...}`), 기대 출력은 채점기가 계산해 준다. `judge: "leetcode"` 가 프런트에
그 경로를 알린다. `code_snippets` 는 뷰어 언어별 공식 코드 스텁(python3·cpp 는 `class Solution`, mysql 은 SQL 주석 한 줄)이고,
`statement_text_ko` 는 번역 본문의 텍스트판(GitHub README 용)이다.
"""
import asyncio

import clients as api_client
from clients.leetcode import lc_html_to_text, normalize_leetcode_problem_ref
from clients.leetcode_judge import JUDGE_LANGUAGES, split_example_cases
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
        # GitHub push 의 README 본문. 프런트가 push 요청의 description 으로 보낸다 — 없으면 서버가
        # 영문 원문을 새로 긁어 넣는다(CF 의 statement_sections_ko 와 같은 역할).
        "statement_text_ko": lc_html_to_text(content_ko) if content_ko else "",
        "url": raw["url"],
        "translated": translated,
        "judge": "leetcode",
        "samples": [{"input": case}
                    for case in split_example_cases(raw.get("example_testcases", ""), raw.get("meta_data", ""))],
        # 에디터 초기 코드. 임시 저장본이 없을 때만 프런트가 채운다. 뷰어 언어 select 값 = 채점 언어라
        # 그 밖의 스텁은 싣지 않는다.
        "code_snippets": {lang: code for lang, code in (raw.get("code_snippets") or {}).items()
                          if lang in JUDGE_LANGUAGES},
    }
    # 번역 성공 시 영구 캐시, 실패 시 60초 뒤 재시도. 본문이 없는 유료 문제는 번역할 것이 없어 영구 캐시한다.
    problem_cache.cache_set(cache_key, result, translated or not html)
    return result
