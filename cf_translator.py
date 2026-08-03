import re

from openai import OpenAI

from clients.codeforces import TEX_IMG_MARKER_RE
from config import settings

_MAX_TOKENS = settings.openai_max_tokens or 2000
_TEMPERATURE = settings.openai_temperature
_API_TIMEOUT = settings.openai_timeout

_INDEX_MARKER_RE = re.compile(r'⟦img:(\d+)⟧')


def _mask_image_markers(text: str) -> tuple[str, list[str]]:
    """수식 이미지 마커의 URL 을 짧은 번호로 바꾼다.

    마커 URL 은 40자 hex 해시라 LLM 이 한 글자만 틀려도 깨진 이미지가 된다.
    번호만 보내면 복사 실패 가능성이 사실상 사라지고 토큰도 아낀다.
    """
    urls: list[str] = []

    def _to_index(match: re.Match) -> str:
        urls.append(match.group(1))
        return f"⟦img:{len(urls) - 1}⟧"

    return TEX_IMG_MARKER_RE.sub(_to_index, text), urls


def _unmask_image_markers(text: str, urls: list[str]) -> str:
    """번호 마커를 원래 URL 로 되돌린다. 없는 번호(LLM 이 지어낸 것)는 버린다."""
    def _to_url(match: re.Match) -> str:
        index = int(match.group(1))
        return f"⟦img:{urls[index]}⟧" if index < len(urls) else ""

    return _INDEX_MARKER_RE.sub(_to_url, text)


def translate_cf_text(text: str, title: str) -> str:
    """번역 성공 시 번역문, 응답이 비어 있으면 원문을 그대로 반환. API 예외는 전파 (캐시 오염 방지).

    입력은 이미 clients.codeforces.normalize_cf_math 를 거친 $…$ 형식이다.
    """
    text, image_urls = _mask_image_markers(text)
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
                "5. If the text is already in Korean or has nothing to translate, return it as-is. "
                "6. Keep every ⟦img:N⟧ marker (N is a digit) exactly as-is, in place — "
                "   it is a formula image placeholder. Do not translate, renumber, or drop it, "
                "   and never wrap it in $...$."
            )},
            {"role": "user", "content": f"Problem: {title}\n\nTranslate this text:\n\n{text}"},
        ],
        max_tokens=_MAX_TOKENS,
        temperature=_TEMPERATURE,
        timeout=_API_TIMEOUT,
    )
    # text 는 이 시점에 마스킹된 상태이므로 폴백이든 번역문이든 똑같이 되돌린다.
    result = resp.choices[0].message.content.strip() or text
    return _unmask_image_markers(result, image_urls)
