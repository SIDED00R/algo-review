import time
import themes as theme_service
from fastapi import APIRouter
from demo_mode import IS_DEMO, DEMO_THEMES

router = APIRouter()

# 테마 대표 문제는 거의 변하지 않으므로 Codeforces API 반복 호출을 막기 위해 캐시한다.
_CACHE_TTL = 3600           # 전 테마 정상 시 캐시 수명(초)
_FALLBACK_TTL = 60          # 일부/전부 실패 시 재시도까지 대기(초)
_cache: dict = {"data": None, "expires": 0.0}


@router.get("/api/themes")
def get_themes():
    if IS_DEMO:
        return {"themes": DEMO_THEMES}

    now = time.time()
    if _cache["data"] is not None and now < _cache["expires"]:
        return {"themes": _cache["data"]}

    data = theme_service.get_theme_problems()
    # 일부 테마라도 비면(일시적 실패) 짧게 캐시해 복구 후 곧 다시 채워지게 한다.
    all_ok = all(t["problems"] for t in data)
    _cache["data"] = data
    _cache["expires"] = now + (_CACHE_TTL if all_ok else _FALLBACK_TTL)
    return {"themes": data}
