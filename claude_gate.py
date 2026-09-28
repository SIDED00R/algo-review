"""LLM 제공자 선택 — 소유자 요청이면 Claude 구독으로 답을 받고, 아니거나 실패하면 None.

None 을 받은 호출부는 OpenAI 호환 엔드포인트(llm_client)로 진행한다. 구독 사용량 한도·
토큰 만료·CLI 실패가 리뷰와 번역을 멈추지 않게 실패 사유는 로그로만 남긴다.
"""
import logging

import claude_client
from owner_access import is_owner_request

logger = logging.getLogger("uvicorn.error")


def claude_answer(system_prompt: str, user_prompt: str) -> str | None:
    if not (is_owner_request() and claude_client.is_configured()):
        return None
    try:
        answer = claude_client.complete(system_prompt, user_prompt)
    except Exception as e:
        logger.warning("Claude 호출 실패 — OpenAI 호환 엔드포인트로 넘어간다: %s: %s",
                       type(e).__name__, e)
        return None
    logger.info("Claude 구독으로 답함 (%d자)", len(answer))
    return answer
