import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, TimeoutError as SQLTimeoutError

import db
import warmup
from config import settings
from db.connection import session_scope
from demo_mode import IS_DEMO
from routes import (
    auth, review, pending_review, rereview, github_push, problem, execute, recommend,
    history, solved, import_github, import_boj, import_codeforces,
    stats, report, themes,
)

logger = logging.getLogger("uvicorn.error")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if IS_DEMO:
        import demo_seed
        demo_seed.seed()
    else:
        try:
            db.run_migrations()
        except OperationalError as e:
            # 온디맨드 DB가 정지 상태여도 기동은 계속한다 — 배포·콜드스타트가 DB 상태에 묶이면 안 된다.
            # **연결 실패만** 흘려보낸다. except Exception 으로 넓히면 잘못된 리비전·DDL 오류·
            # 다중 인스턴스의 upgrade head 경합까지 warning 한 줄로 덮고, 새 컬럼이 없는
            # 스키마로 서비스하다 나중에 원인 불명 500 이 난다.
            logger.warning("DB 연결 실패로 마이그레이션 건너뜀 (온디맨드 정지 상태일 수 있음): %s", e)
    # 테마 캐시 예열은 기동을 막지 않게 백그라운드로 — 데모는 외부 API를 치지 않는다.
    warm_task = None if IS_DEMO else asyncio.create_task(warmup.warm_theme_caches())
    yield
    if warm_task and not warm_task.done():
        warm_task.cancel()


app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천", lifespan=lifespan)


# 커넥션 풀 고갈은 OperationalError 가 아니라 sqlalchemy.exc.TimeoutError 다 — 같은
# "지금은 DB 를 못 쓴다" 상황이므로 함께 503 으로 보낸다.
@app.exception_handler(SQLTimeoutError)
async def _pool_timeout_handler(request: Request, exc: SQLTimeoutError):
    logger.warning("DB 커넥션 풀 대기 시간 초과: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "데이터베이스가 혼잡합니다. 잠시 후 다시 시도해주세요."},
    )


@app.exception_handler(OperationalError)
async def _db_unavailable_handler(request: Request, exc: OperationalError):
    # 온디맨드 DB 정지 등으로 연결이 안 되면 500 대신 503 + 안내를 준다.
    logger.warning("DB 연결 실패: %s", exc)
    return JSONResponse(
        status_code=503,
        content={"detail": "데이터베이스에 연결할 수 없습니다 (온디맨드 정지 상태일 수 있습니다). 잠시 후 다시 시도해주세요."},
    )


@app.exception_handler(Exception)
async def _unhandled_handler(request: Request, exc: Exception):
    # Starlette 의 ServerErrorMiddleware 가 응답 전송 후 예외를 항상 재-raise 하고,
    # uvicorn 이 같은 로거로 트레이스백을 한 번 더 남긴다. 여기서 exception() 을 쓰면
    # 미처리 예외 1건당 트레이스백이 2개가 되므로 요약만 남긴다.
    logger.error("처리되지 않은 예외: %r", exc)
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


# 목록 응답이 수 MB 가 된다(실측: reviews 5만 행에서 /api/reviews/grouped 7.37MB).
# JSON 은 압축률이 10배 안팎이라 전송 시간이 그만큼 줄고 압축 CPU 는 100ms 수준이다.
# minimum_size 아래(대부분의 API 응답)는 그대로 통과한다.
app.add_middleware(GZipMiddleware, minimum_size=1024)


allowed_origins = [
    origin.strip()
    for origin in settings.cors_origins.split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)

STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

app.include_router(auth.router)
app.include_router(review.router)
app.include_router(pending_review.router)
app.include_router(rereview.router)
app.include_router(github_push.router)
app.include_router(problem.router)
app.include_router(execute.router)
app.include_router(recommend.router)
app.include_router(history.router)
app.include_router(solved.router)
app.include_router(import_github.router)
app.include_router(import_boj.router)
app.include_router(import_codeforces.router)
app.include_router(stats.router)
app.include_router(report.router)
app.include_router(themes.router)


@app.get("/health")
def health():
    # 경로는 /health — Cloud Run GFE 가 정확히 /healthz 를 가로채 컨테이너까지 오지 않는다.
    # 상태코드는 항상 200 — Cloud Run 프로브가 온디맨드 DB 정지에 묶이면 안 된다.
    # db 필드는 best-effort 진단용.
    db_status = "unavailable"
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        pass
    return {"status": "ok", "db": db_status}


# 정적 자산 캐시 버전 — index.html 의 `?v=__V__` 를 기동 시 한 번 치환한다.
# Cloud Run 이 리비전마다 넣어 주는 K_REVISION 을 토큰으로 쓰므로 배포하면 로컬 자산 URL 이
# 한꺼번에 갱신된다. 손으로 적는 값이 아니라 배포마다 자동으로 바뀌는 값을 쓴다.
# 개수는 적지 않는다 — 자산이 늘 때마다 주석만 뒤처진다.
# 로컬에는 K_REVISION 이 없어 static/ 전체 파일 중 가장 최근 mtime 으로 대체한다 —
# index.html 만 보면 JS/CSS 만 고쳤을 때 토큰이 그대로라 브라우저가 옛 자산을 계속 쓴다.
_ASSET_VERSION = os.getenv("K_REVISION") or str(int(max(
    p.stat().st_mtime for p in STATIC_DIR.rglob("*") if p.is_file()
)))
_INDEX_HTML = (STATIC_DIR / "index.html").read_text(encoding="utf-8").replace("__V__", _ASSET_VERSION)


@app.get("/")
def index():
    # 셸 문서는 항상 재검증한다 — 자산 URL 이 이 안에 박혀 있어 이게 캐시되면 새 버전이 안 보인다.
    return HTMLResponse(_INDEX_HTML, headers={"Cache-Control": "no-cache"})
