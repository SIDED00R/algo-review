import os
import asyncio
import re
import time
import requests
from lxml import etree
from fastapi import APIRouter, HTTPException
from demo_mode import IS_DEMO, DEMO_CF_PROBLEM
import clients as api_client

_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "2000"))
_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.3"))
_API_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT", "15"))

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


def _normalize_cf_math(text: str) -> str:
    return re.sub(r'\$\$\$(.+?)\$\$\$', r'$\1$', text, flags=re.DOTALL)


def _translate_cf_text(text: str, title: str) -> str:
    """번역 성공 시 번역문 반환. 실패 시 예외를 그대로 전파 (캐시 오염 방지)."""
    from openai import OpenAI as _OpenAI
    text = _normalize_cf_math(text)
    client = _OpenAI(api_key=os.environ.get("OPENAI_API_KEY", ""))
    resp = client.chat.completions.create(
        model=os.environ.get("OPENAI_MODEL", "gpt-4o-mini"),
        messages=[
            {"role": "system", "content": (
                "You are a competitive programming translator. "
                "Translate the given text segment from a Codeforces problem into natural Korean. "
                "IMPORTANT RULES: "
                "1. Always return the full translated text. Never return empty output. "
                "2. Wrap ALL mathematical expressions, variables, and constraints in LaTeX delimiters: "
                "   use $...$ for inline math (e.g., $n$, $1 \\le n \\le 10^5$, $x_i$) "
                "   and $$...$$ for display math (block equations only). "
                "   CRITICAL: Each $...$ must open and close on the SAME LINE — never put a newline inside $...$. "
                "3. Do NOT add any section headers or labels (e.g., do not write '문제:', '입력:', '출력:'). "
                "4. Translate all English prose naturally to Korean. "
                "5. If the text is already in Korean or has nothing to translate, return it as-is."
            )},
            {"role": "user", "content": f"Problem: {title}\n\nTranslate this text:\n\n{text}"},
        ],
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        timeout=_API_TIMEOUT,
    )
    result = resp.choices[0].message.content.strip()
    return result if result else text


@router.get("/api/problem/cf/{problem_ref}")
async def get_cf_problem(problem_ref: str):
    if IS_DEMO:
        return DEMO_CF_PROBLEM

    ref_key = problem_ref.strip().upper()
    cached = _cache_get(ref_key)
    if cached is not None:
        return cached

    m = re.match(r'^(\d+)([A-Za-z]\d*)$', problem_ref.strip())
    if not m:
        raise HTTPException(400, "잘못된 문제 번호 형식 (예: 4A, 1234B)")
    contest_id, index = m.group(1), m.group(2).upper()

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    try:
        resp = requests.get(url, timeout=10, headers={
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
        })
        resp.raise_for_status()
    except Exception as e:
        raise HTTPException(502, f"CF 페이지 로딩 실패: {e}")

    tree = etree.fromstring(resp.text.encode(), etree.HTMLParser())

    def _limit_value(xpath_expr: str) -> str:
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return ""
        el = nodes[0]
        prop_nodes = el.xpath('.//*[contains(@class,"property-title")]')
        prop_text = " ".join(prop_nodes[0].itertext()).strip() if prop_nodes else ""
        full_text = " ".join(el.itertext()).strip()
        return full_text.replace(prop_text, "", 1).strip()

    title = api_client.cf_xpath_text(tree, '//div[@class="title"]') or f"CF {problem_ref}"
    time_limit   = _limit_value('//div[contains(@class,"time-limit")]')
    memory_limit = _limit_value('//div[contains(@class,"memory-limit")]')

    BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'
    statement_text = api_client.cf_xpath_text(tree, f'{BASE}/div[2]')
    input_text     = api_client.cf_xpath_text(tree, f'{BASE}/div[3]')
    output_text    = api_client.cf_xpath_text(tree, f'{BASE}/div[4]')

    note_nodes = tree.xpath('//*[contains(@class,"note")]')
    note_text = " ".join(note_nodes[0].itertext()).strip() if note_nodes else ""

    samples = []
    sample_container = tree.xpath(f'{BASE}/div[5]')
    if sample_container:
        sc = sample_container[0]
        inp_pres = sc.xpath('.//div[contains(@class,"input")]//pre')
        out_pres = sc.xpath('.//div[contains(@class,"output")]//pre')
        for inp_pre, out_pre in zip(inp_pres, out_pres):
            samples.append({
                "input":  "\n".join(inp_pre.itertext()).strip(),
                "output": "\n".join(out_pre.itertext()).strip(),
            })

    async def _translate_async(text: str) -> tuple[str, bool]:
        """(번역문, 성공여부) 반환 — 실패 시 원문과 False."""
        if not text:
            return "", True
        try:
            translated = await asyncio.to_thread(_translate_cf_text, text, title)
            return translated, True
        except Exception:
            return text, False

    (statement_ko, s_ok), (input_ko, i_ok), (output_ko, o_ok), (note_ko, n_ok) = (
        await asyncio.gather(
            _translate_async(statement_text),
            _translate_async(input_text),
            _translate_async(output_text),
            _translate_async(note_text),
        )
    )

    result = {
        "title": title,
        "time_limit": time_limit,
        "memory_limit": memory_limit,
        "statement_sections_ko": {
            "statement": statement_ko,
            "input":     input_ko,
            "output":    output_ko,
            "note":      note_ko,
        },
        "samples": samples,
        "url": url,
        "contest_id": contest_id,
        "index": index,
    }
    all_ok = s_ok and i_ok and o_ok and n_ok
    # 번역 성공 시 영구 캐시, 실패 시 60초 단기 TTL — retry storm 방지
    _cache_set(ref_key, result, all_ok)
    return result
