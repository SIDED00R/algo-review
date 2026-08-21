"""OpenAI 호환 클라이언트 싱글턴과 응답 가드 — LLM 을 호출하는 모듈이 공유한다.

analyzer 에만 있던 두 조치(싱글턴 · choices 가드)를 cf_translator 가 갖지 못해,
"문제 뷰어는 한 요청에 섹션 4개를 동시 번역한다" 는 싱글턴의 근거가 정작 그 워크로드에
적용되지 않고 있었다(analyzer.analyze_code 는 요청당 1회만 불린다). 여기로 올려
새 호출 지점이 생겨도 같은 보장을 받게 한다.
"""
import threading

from openai import OpenAI

from config import settings

# openai SDK 기본값은 read 600s·재시도 2회 — 제공자가 멎으면 워커 스레드가 수십 분 잡힌다.
# timeout 만 줄이면 실효 상한이 3×timeout + 백오프가 되므로 재시도 횟수도 함께 못박는다.
# 둘 다 설정으로 노출한다 — 한쪽만 환경변수면 운영에서 조절할 수 있는 축이 반쪽이다.
_API_TIMEOUT = settings.openai_timeout
_MAX_RETRIES = settings.openai_max_retries

# 클라이언트는 프로세스에 하나만 둔다 — 호출마다 새로 만들면 httpx 커넥션 풀과 TLS
# 핸드셰이크를 매번 버린다. settings 는 기동 시 고정되므로 재생성할 이유가 없다.
_client = None
_client_lock = threading.Lock()


def get_client() -> OpenAI:
    global _client
    if _client is not None:
        return _client
    with _client_lock:
        if _client is None:
            _client = OpenAI(api_key=settings.openai_api_key,
                             base_url=settings.openai_base_url or None,
                             timeout=_API_TIMEOUT, max_retries=_MAX_RETRIES)
    return _client


def require_choice(response) -> None:
    """choices 가 비면 인덱싱이 IndexError 로 새어 "list index out of range" 라는 해독
    불가 500 이 된다. .env.example 이 Gemini 호환 엔드포인트를 1급 대안으로 안내하므로
    (응답 형태가 미묘하게 다를 수 있다) 현실적인 경계다. **인덱싱보다 먼저 호출해야 한다.**
    """
    if not getattr(response, "choices", None):
        raise ValueError("AI 응답에 결과가 없습니다. 제공자 설정(OPENAI_BASE_URL·모델)을 확인해주세요.")


def choice_text(response) -> str:
    """첫 choice 의 본문. content 가 None 인 응답(도구 호출만 담긴 경우 등)도 있으므로
    `.strip()` 을 바로 붙이지 않는다 — AttributeError 로 새면 원인을 알 수 없다."""
    require_choice(response)
    return (response.choices[0].message.content or "").strip()
