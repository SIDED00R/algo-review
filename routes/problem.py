import time
import asyncio
import requests

import clients as api_client
from clients.codeforces import normalize_codeforces_problem_ref
from fastapi import APIRouter, HTTPException
from routes.helpers import upstream_failure
from demo_mode import IS_DEMO, DEMO_CF_PROBLEM
from cf_translator import translate_cf_text

router = APIRouter()

# problem_ref → {"result": dict, "expires": float|None}
# expires=None: 영구 캐시(번역 성공), expires=timestamp: 단기 TTL(번역 실패 — 60초 후 재시도)
_PROBLEM_CACHE_MAX = 200
_PROBLEM_CACHE: dict[str, dict] = {}
_FALLBACK_TTL = 60  # 번역 실패 시 재시도까지 대기 시간(초)


def _cache_get(ref_key: str) -> dict | None:
    entry = _PROBLEM_CACHE.get(ref_key)
    if entry is None:
        return None
    expires = entry.get("expires")
    if expires is not None and time.time() > expires:
        del _PROBLEM_CACHE[ref_key]
        return None
    return entry["result"]


def _cache_set(ref_key: str, result: dict, translation_ok: bool) -> None:
    # 이미 있는 키를 갱신할 때는 항목 수가 늘지 않는다 — 그때도 축출하면
    # 번역 재시도(60초 TTL 만료 후)마다 무관한 문제 하나가 캐시에서 밀려난다.
    if ref_key not in _PROBLEM_CACHE and len(_PROBLEM_CACHE) >= _PROBLEM_CACHE_MAX:
        _PROBLEM_CACHE.pop(next(iter(_PROBLEM_CACHE)))
    _PROBLEM_CACHE[ref_key] = {
        "result": result,
        "expires": None if translation_ok else time.time() + _FALLBACK_TTL,
    }


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
    cached = _cache_get(ref_key)
    if cached is not None:
        return cached

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
        try:
            translated = await asyncio.to_thread(translate_cf_text, text, title)
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
    _cache_set(ref_key, result, all_ok)
    return result
