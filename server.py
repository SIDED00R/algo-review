import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

import db
from routes import (
    auth, review, github_push, problem, execute, recommend,
    history, solved, import_github, import_boj, import_codeforces,
    stats, report, themes,
)

app = FastAPI(title="알고리즘 코드 리뷰 & 문제 추천")

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

if os.environ.get("DEMO_MODE", "false").lower() == "true":
    import demo_seed
    demo_seed.seed()
else:
    db.init_db()

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
