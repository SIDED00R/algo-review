import asyncio
import requests

import clients as api_client
from clients.codeforces import normalize_codeforces_problem_ref
from fastapi import APIRouter, HTTPException
from routes import problem_cache
from routes.helpers import upstream_failure
from demo_mode import IS_DEMO, DEMO_CF_PROBLEM
from statement_translator import MAX_TRANSLATE_LENGTH, translate_statement

router = APIRouter()


@router.get("/api/problem/cf/{problem_ref}")
async def get_cf_problem(problem_ref: str):
    if IS_DEMO:
        return DEMO_CF_PROBLEM

    # 정규화한 형태를 캐시 키로 쓴다 — `4A`·`4/A`·`4-A` 는 같은 문제인데 대문자화만
    # 하면 항목이 셋으로 갈리고, 404 메시지도 입력에 따라 흔들린다.
    try:
        ref_key = "".join(str(part) for part in normalize_codeforces_problem_ref(problem_ref))
    except ValueError:
        raise HTTPException(status_code=400, detail="잘못된 문제 번호 형식 (예: 4A, 1234B)") from None
    cache_key = f"cf:{ref_key}"
    return await problem_cache.run_deduplicated(
        cache_key, lambda: _scrape_and_translate(cache_key, ref_key, problem_ref))


async def _scrape_and_translate(cache_key: str, ref_key: str, problem_ref: str) -> dict:
    try:
        # 동기 HTTP 호출(최대 10초)이라 이벤트 루프를 막지 않게 스레드로 뺀다 — 아래 번역과 같은 이유.
        raw = await asyncio.to_thread(api_client.scrape_cf_problem, problem_ref)
    except ValueError:
        raise HTTPException(400, "잘못된 문제 번호 형식 (예: 4A, 1234B)")
    except requests.HTTPError as e:
        # 형식은 맞지만 없는 문제다 — 502 는 절대 성공하지 않을 재시도를 유도한다.
        if e.response is not None and e.response.status_code == 404:
            raise HTTPException(404, f"Codeforces 에 없는 문제입니다: {ref_key}") from None
        raise upstream_failure("CF 페이지 로딩 실패", e)
    except Exception as e:
        raise upstream_failure("CF 페이지 로딩 실패", e)

    title = raw["title"]

    async def _translate_async(text: str) -> tuple[str, bool]:
        if not text:
            return "", True
        if len(text) > MAX_TRANSLATE_LENGTH:
            # 유료 호출이다 — 상한이 없으면 긴 본문을 순회하는 것만으로 과금이 늘어난다.
            # 상한을 넘으면 원문을 그대로 보여준다(번역 실패와 같은 처리).
            return text, False
        try:
            translated = await asyncio.to_thread(translate_statement, text, title, source="Codeforces")
            return translated, True
        except Exception:
            return text, False

    (statement_ko, s_ok), (input_ko, i_ok), (output_ko, o_ok), (note_ko, n_ok) = (
        await asyncio.gather(
            _translate_async(raw["statement"]),
            _translate_async(raw["input"]),
            _translate_async(raw["output"]),
            _translate_async(raw["note"]),
        )
    )

    result = {
        "title": title,
        "time_limit": raw["time_limit"],
        "memory_limit": raw["memory_limit"],
        "statement_sections_ko": {
            "statement": statement_ko,
            "input":     input_ko,
            "output":    output_ko,
            "note":      note_ko,
        },
        "samples": raw["samples"],
        "url": raw["url"],
        "contest_id": raw["contest_id"],
        "index": raw["index"],
    }
    all_ok = s_ok and i_ok and o_ok and n_ok
    # 번역 성공 시 영구 캐시, 실패 시 60초 단기 TTL — retry storm 방지
    problem_cache.cache_set(cache_key, result, all_ok)
    return result
