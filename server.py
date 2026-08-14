import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import text
from sqlalchemy.exc import OperationalError

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
        except Exception as e:
            # 온디맨드 DB가 정지 상태여도 기동은 계속한다 — 배포·콜드스타트가 DB 상태에 묶이면 안 된다.
            logger.warning("마이그레이션 실패로 건너뜀 (온디맨드 DB 정지 등 연결 문제일 수 있음): %s", e)
    # 테마 캐시 예열은 기동을 막지 않게 백그라운드로 — 데모는 외부 API를 치지 않는다.
    warm_task = None if IS_DEMO else asyncio.create_task(warmup.warm_theme_caches())
    yield
    if warm_task and not warm_task.done():
        warm_task.cancel()


app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천", lifespan=lifespan)


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
    logger.exception("처리되지 않은 예외")
    return JSONResponse(status_code=500, content={"detail": "서버 내부 오류가 발생했습니다."})


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
STATIC_DIR.mkdir(exist_ok=True)
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
    # 상태코드는 항상 200 — Cloud Run 프로브가 온디맨드 DB 정지에 묶이면 안 된다(#67).
    # db 필드는 best-effort 진단용.
    db_status = "unavailable"
    try:
        with session_scope() as session:
            session.execute(text("SELECT 1"))
        db_status = "ok"
    except Exception:
        pass
    return {"status": "ok", "db": db_status}


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
