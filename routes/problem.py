import time
import asyncio
import clients as api_client
from fastapi import APIRouter, HTTPException
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
    if len(_PROBLEM_CACHE) >= _PROBLEM_CACHE_MAX:
        _PROBLEM_CACHE.pop(next(iter(_PROBLEM_CACHE)))
    _PROBLEM_CACHE[ref_key] = {
        "result": result,
        "expires": None if translation_ok else time.time() + _FALLBACK_TTL,
    }


@router.get("/api/problem/cf/{problem_ref}")
async def get_cf_problem(problem_ref: str):
    if IS_DEMO:
        return DEMO_CF_PROBLEM

    ref_key = problem_ref.strip().upper()
    cached = _cache_get(ref_key)
    if cached is not None:
        return cached

    try:
        raw = api_client.scrape_cf_problem(problem_ref)
    except ValueError:
        raise HTTPException(400, "잘못된 문제 번호 형식 (예: 4A, 1234B)")
    except Exception as e:
        raise HTTPException(502, f"CF 페이지 로딩 실패: {e}")

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
