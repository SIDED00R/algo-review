import themes as theme_service
from fastapi import APIRouter, HTTPException, Response
from demo_mode import IS_DEMO, DEMO_THEME_LIST, DEMO_THEME_PROBLEMS

router = APIRouter()


@router.get("/api/themes")
def get_themes(response: Response):
    # 테마 목록은 정적이라 브라우저 캐시를 허용한다.
    response.headers["Cache-Control"] = "public, max-age=3600"
    themes = DEMO_THEME_LIST if IS_DEMO else theme_service.get_theme_list()
    return {"themes": themes, "platforms": list(theme_service.PLATFORMS)}


@router.get("/api/themes/{theme_id}/problems")
def get_theme_problems(theme_id: str, response: Response, platform: str = "codeforces"):
    # 푼 문제 제외 결과라 사용자 상태에 의존 — 브라우저 캐시 금지(클라이언트 캐싱은 localStorage 계층이 담당).
    response.headers["Cache-Control"] = "no-store"
    if platform not in theme_service.PLATFORMS:
        raise HTTPException(status_code=400, detail="지원하지 않는 플랫폼입니다.")

    if IS_DEMO:
        data = DEMO_THEME_PROBLEMS.get((platform, theme_id))
        if data is None:
            raise HTTPException(status_code=404, detail="존재하지 않는 테마입니다.")
        return data

    theme = theme_service.find_theme(theme_id)
    if theme is None:
        raise HTTPException(status_code=404, detail="존재하지 않는 테마입니다.")
    return theme_service.build_theme_response(platform, theme)
