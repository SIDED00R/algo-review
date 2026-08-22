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
            try:
                # 신선도 확인도 DB 를 친다 — try 밖에 두면 온디맨드 DB 정지 상태에서
                # 첫 항목의 OperationalError 가 이 코루틴을 통째로 끝낸다. 그 태스크는
                # fire-and-forget 이라 "never retrieved" 경고조차 뜨지 않아 무흔적이다.
                if await asyncio.to_thread(theme_service.theme_pool_is_fresh, platform, theme):
                    continue   # 외부 호출이 없다 — 예절 간격도 필요 없다
                await asyncio.to_thread(theme_service.get_theme_problem_pool, platform, theme)
            except Exception as e:
                logger.warning("테마 캐시 예열 실패 %s/%s: %s", platform, theme["id"], e)
            await asyncio.sleep(WARMUP_DELAY_SEC)
    logger.info("테마 캐시 예열 완료")
