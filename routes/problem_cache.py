"""문제 뷰어 응답의 프로세스 캐시 + 같은 키의 동시 요청 병합.

`/api/problem/cf/{ref}` 가 쓴다. 캐시 키는 라우터가 플랫폼 접두사를 붙여 만든다(`cf:4A`).
번역 성공 결과는 만료 없이, 실패 결과는 60초 뒤 재시도하도록 짧게 둔다.
"""
import asyncio
import time

_CACHE_MAX = 200
# key → {"result": dict, "expires": float|None}
# expires=None: 영구 캐시(번역 성공), expires=timestamp: 단기 TTL(번역 실패 — 60초 후 재시도)
_CACHE: dict[str, dict] = {}
_FALLBACK_TTL = 60  # 번역 실패 시 재시도까지 대기 시간(초)

# key → 진행 중인 수집·번역 작업. 캐시 미스가 겹치면 한 요청만 실제로 수집하고 나머지는
# 그 결과를 기다린다 — 캐시에 들어가기 전 구간(스크래핑 + 유료 번역)이 수 초~십수 초다.
# 인스턴스 로컬이다 — 다른 인스턴스로 라우팅된 요청은 각자 수집한다(캐시와 같은 한계).
_IN_FLIGHT: dict[str, asyncio.Task] = {}


def cache_get(key: str) -> dict | None:
    entry = _CACHE.get(key)
    if entry is None:
        return None
    expires = entry.get("expires")
    if expires is not None and time.time() > expires:
        del _CACHE[key]
        return None
    return entry["result"]


def cache_set(key: str, result: dict, translation_ok: bool) -> None:
    # 이미 있는 키를 갱신할 때는 항목 수가 늘지 않는다 — 그때도 축출하면
    # 번역 재시도(60초 TTL 만료 후)마다 무관한 문제 하나가 캐시에서 밀려난다.
    if key not in _CACHE and len(_CACHE) >= _CACHE_MAX:
        _CACHE.pop(next(iter(_CACHE)))
    _CACHE[key] = {
        "result": result,
        "expires": None if translation_ok else time.time() + _FALLBACK_TTL,
    }


def _release_in_flight(key: str, task: asyncio.Task) -> None:
    """끝난 작업을 맵에서 지운다 — 실패·취소도 지운다(다음 요청이 다시 수집한다)."""
    _IN_FLIGHT.pop(key, None)
    if not task.cancelled():
        task.exception()  # 대기자가 모두 끊긴 경우의 "never retrieved" 경고를 막는다


async def run_deduplicated(key: str, factory) -> dict:
    """캐시에 있으면 그 값을, 없으면 factory() 작업을 한 번만 띄워 그 결과를 돌려준다.

    결과의 캐시 저장은 factory 가 cache_set 으로 직접 한다 — 번역 성공 여부를 아는 쪽이다.
    """
    cached = cache_get(key)
    if cached is not None:
        return cached

    task = _IN_FLIGHT.get(key)
    if task is None:
        # 이벤트 루프 단일 스레드라 조회~등록 사이에 다른 요청이 끼어들지 않는다.
        task = asyncio.ensure_future(factory())
        _IN_FLIGHT[key] = task
        task.add_done_callback(lambda t, k=key: _release_in_flight(k, t))
    # shield 로 대기자를 개시자의 취소에서 떼어낸다 — 개시 요청이 끊겨도 작업과 다른 대기자는 계속된다.
    return await asyncio.shield(task)
