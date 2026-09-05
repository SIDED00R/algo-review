import re

from clients.codeforces import TEX_IMG_MARKER_RE
from config import settings
from llm_client import choice_text, get_client, require_choice

_MAX_TOKENS = settings.openai_max_tokens or 2000
_TEMPERATURE = settings.openai_temperature

# 번역 입력 상한. 출력만 제한하는 _MAX_TOKENS 와 달리 **입력** 토큰 비용을 막는다.
# CF 본문 한 섹션이 이 길이를 넘는 경우는 거의 없다.
MAX_TRANSLATE_LENGTH = 20_000

_INDEX_MARKER_RE = re.compile(r'⟦img:(\d+)⟧')


def _mask_image_markers(text: str) -> tuple[str, list[str]]:
    """수식 이미지 마커의 URL 을 짧은 번호로 바꾼다.

    마커 URL 은 40자 hex 해시라 LLM 이 옮겨 적다 한 글자만 틀려도 깨진 이미지가 된다.
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
    """번역 성공 시 번역문, 응답이 비어 있으면 원문을 그대로 반환. API 예외는 전파한다.

    응답이 max_tokens 에 걸려 잘린 경우도 성공으로 간주해 잘린 번역문 + 안내 문구를 반환한다.
    routes/problem.py 는 성공 결과를 만료 없이 캐시한다.

    입력은 이미 clients.codeforces.normalize_cf_math 를 거친 $…$ 형식이다.
    """
    text, image_urls = _mask_image_markers(text)
    resp = get_client().chat.completions.create(
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
    )
    require_choice(resp)
    if resp.choices[0].finish_reason == "length":
        # 응답이 max_tokens 에 걸려 문장 중간에서 잘렸다. 잘린 번역을 성공으로 간주해
        # 캐시하고, 잘렸다는 사실만 사용자에게 알린다.
        partial = choice_text(resp) or text
        return _unmask_image_markers(partial, image_urls) + \
            "\n\n_(⚠️ 문제가 너무 길어 번역이 일부 생략되었습니다.)_"

    # text 는 이 시점에 마스킹된 상태다. 폴백이든 번역문이든 똑같이 되돌린다.
    result = choice_text(resp) or text
    return _unmask_image_markers(result, image_urls)
