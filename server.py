import asyncio
import logging
import os
from contextlib import asynccontextmanager
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import db
import warmup
from demo_mode import IS_DEMO
from routes import (
    auth, review, github_push, problem, execute, recommend,
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
            db.init_db()
        except Exception as e:
            # 온디맨드 DB가 정지 상태여도 기동은 계속한다 — 배포·콜드스타트가 DB 상태에 묶이면 안 된다.
            logger.warning("DB 연결 실패로 스키마 초기화 건너뜀 (온디맨드 정지 상태일 수 있음): %s", e)
    # 테마 캐시 예열은 기동을 막지 않게 백그라운드로 — 데모는 외부 API를 치지 않는다.
    warm_task = None if IS_DEMO else asyncio.create_task(warmup.warm_theme_caches())
    yield
    if warm_task and not warm_task.done():
        warm_task.cancel()


app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천", lifespan=lifespan)

allowed_origins = [
    origin.strip()
    for origin in os.environ.get("CORS_ORIGINS", "http://localhost:8080").split(",")
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


@app.get("/")
def index():
    return FileResponse(STATIC_DIR / "index.html")
