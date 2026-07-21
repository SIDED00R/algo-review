import re
from openai import OpenAI

from config import settings

_MAX_TOKENS = settings.openai_max_tokens or 2000
_TEMPERATURE = settings.openai_temperature
_API_TIMEOUT = settings.openai_timeout


def _normalize_cf_math(text: str) -> str:
    return re.sub(r'\$\$\$(.+?)\$\$\$', r'$\1$', text, flags=re.DOTALL)


def translate_cf_text(text: str, title: str) -> str:
    """번역 성공 시 번역문, 응답이 비어 있으면 원문을 그대로 반환. API 예외는 전파 (캐시 오염 방지)."""
    text = _normalize_cf_math(text)
    client = OpenAI(api_key=settings.openai_api_key)
    resp = client.chat.completions.create(
        model=settings.openai_model or "gpt-4o-mini",
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
