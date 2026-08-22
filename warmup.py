import asyncio
import logging

import themes as theme_service
from constants import PLATFORMS

logger = logging.getLogger("uvicorn.error")

WARMUP_DELAY_SEC = 0.5  # 외부 API 예절 간격 + 이벤트 루프 양보


async def warm_theme_caches():
    """기동 직후 백그라운드에서 플랫폼×테마 문제 풀 캐시를 채운다.
    신선한 캐시는 get_theme_problem_pool 이 fetch 없이 통과시키므로 반복 기동에 안전하고,
    운영(Cloud SQL)에서는 하루 중 첫 인스턴스만 실제 fetch를 수행한다."""
    for platform in PLATFORMS:
        for theme in theme_service.THEMES:
            if await asyncio.to_thread(theme_service.theme_pool_is_fresh, platform, theme):
                continue   # 외부 호출이 없다 — 예절 간격도 필요 없다
            try:
                await asyncio.to_thread(theme_service.get_theme_problem_pool, platform, theme)
            except Exception as e:
                logger.warning("테마 캐시 예열 실패 %s/%s: %s", platform, theme["id"], e)
            await asyncio.sleep(WARMUP_DELAY_SEC)
    logger.info("테마 캐시 예열 완료")
