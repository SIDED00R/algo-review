import os
import asyncio
import re
import requests
from lxml import etree
from fastapi import APIRouter, HTTPException
from demo_mode import IS_DEMO, DEMO_CF_PROBLEM

_MAX_TOKENS = int(os.environ.get("OPENAI_MAX_TOKENS", "2000"))
_TEMPERATURE = float(os.environ.get("OPENAI_TEMPERATURE", "0.3"))
_API_TIMEOUT = int(os.environ.get("OPENAI_TIMEOUT", "15"))

router = APIRouter()


def _translate_cf_text(text: str, title: str) -> str:
    try:
        from openai import OpenAI as _OpenAI
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
                    "   and $$...$$ for display math. "
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
    except Exception:
        return text


@router.get("/api/problem/cf/{problem_ref}")
async def get_cf_problem(problem_ref: str):
    if IS_DEMO:
        return DEMO_CF_PROBLEM

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

    def _xpath_text(expr: str) -> str:
        nodes = tree.xpath(expr)
        if not nodes:
            return ""
        el = nodes[0]
        for st in el.xpath('.//*[contains(@class,"section-title")]'):
            parent = st.getparent()
            if parent is not None:
                parent.remove(st)
        return " ".join(el.itertext()).strip()

    def _limit_value(xpath_expr: str) -> str:
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return ""
        el = nodes[0]
        prop_nodes = el.xpath('.//*[contains(@class,"property-title")]')
        prop_text = " ".join(prop_nodes[0].itertext()).strip() if prop_nodes else ""
        full_text = " ".join(el.itertext()).strip()
        return full_text.replace(prop_text, "", 1).strip()

    title = _xpath_text('//div[@class="title"]') or f"CF {problem_ref}"
    time_limit   = _limit_value('//div[contains(@class,"time-limit")]')
    memory_limit = _limit_value('//div[contains(@class,"memory-limit")]')

    BASE = '//*[@id="pageContent"]/div[3]/div[2]/div'
    statement_text = _xpath_text(f'{BASE}/div[2]')
    input_text     = _xpath_text(f'{BASE}/div[3]')
    output_text    = _xpath_text(f'{BASE}/div[4]')

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

    async def _translate_async(text):
        if not text:
            return ""
        return await asyncio.to_thread(_translate_cf_text, text, title)

    statement_ko, input_ko, output_ko, note_ko = await asyncio.gather(
        _translate_async(statement_text),
        _translate_async(input_text),
        _translate_async(output_text),
        _translate_async(note_text),
    )

    return {
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
