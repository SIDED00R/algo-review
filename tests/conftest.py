"""테스트 픽스처.

방언은 프로세스 단위로 고정된다 — 한 테스트 실행 안에서 sqlite/postgres 를 섞지 않는다.
CI 는 dialect 매트릭스로 같은 스위트를 두 방언에 각각 돌린다(.github/workflows/deploy.yml).

- sqlite(기본): 테스트마다 tmp 파일 DB 를 새로 만들고 엔진을 리셋한다.
- postgres(CI, DB_TYPE=postgres): 세션 전체가 한 DB 를 공유하고 테스트마다 테이블을 비운다.

in-memory sqlite 는 쓰지 않는다 — alembic 이 별도 커넥션으로 붙으면 스키마가 사라진다.
"""
import os
from datetime import datetime

import pytest
from sqlalchemy import text

import db
from db.connection import dispose_engine, session_scope

# 다른 테스트 모듈도 참조한다 — 목록을 두 곳에 적으면 테이블 추가 시 한쪽만 고쳐진다.
TABLES = ["reviews", "tag_stats", "solved_history", "github_settings", "api_cache"]
IS_POSTGRES = os.environ.get("DB_TYPE", "sqlite").lower() == "postgres"

# IS_DEMO 는 모듈 import 시점에 한 번 결정된다 — 환경에 DEMO_MODE=true 가 있으면
# 비-데모를 전제한 테스트들이 조기 반환에 걸려 원인 불명으로 깨진다(배포 워크플로가
# 데모 서비스에 그 값을 넣으므로 로컬 .env 로 흘러들어올 수 있다).
# 전제를 코드에 못박고, 데모 동작을 검증하는 테스트는 각자 True 로 되돌린다.
_DEMO_AWARE_MODULES = [
    # server 도 넣는다 — client 픽스처가 lifespan 을 실제로 태우므로, 빠뜨리면
    # DEMO_MODE=true 환경에서 demo_seed.seed() 가 테스트 DB 에 행을 심고 마이그레이션이
    # 스킵된다(이 주석이 막으려는 바로 그 상황이 서버 모듈에서만 열려 있었다).
    "server",
    "routes.auth", "routes.execute", "routes.github_push", "routes.import_boj",
    "routes.import_codeforces", "routes.import_github", "routes.pending_review",
    "routes.problem", "routes.recommend", "routes.report", "routes.rereview",
    "routes.review", "routes.solved", "routes.themes",
]


def _truncate_all():
    with session_scope(commit=True) as session:
        for table in TABLES:
            session.execute(text(f"DELETE FROM {table}"))


@pytest.fixture(autouse=True)
def not_demo(monkeypatch):
    """모든 테스트는 비-데모를 전제한다. 데모 경로를 보는 테스트는 스스로 True 로 되돌린다."""
    import importlib
    for name in _DEMO_AWARE_MODULES:
        module = importlib.import_module(name)
        if hasattr(module, "IS_DEMO"):
            monkeypatch.setattr(module, "IS_DEMO", False)


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    if IS_POSTGRES:
        dispose_engine()
        db.run_migrations()
        _truncate_all()
        yield
        _truncate_all()
    else:
        monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
        dispose_engine()
        db.run_migrations()
        yield
        dispose_engine()


@pytest.fixture
def client(monkeypatch):
    """server.app 전체를 얹은 TestClient. lifespan 의 warmup 백그라운드 태스크(외부 API)를
    no-op 으로 막는다. 세 파일이 이 픽스처를 글자 그대로 복제하고 있었다."""
    import server
    import warmup
    from fastapi.testclient import TestClient

    async def _noop():
        return None

    monkeypatch.setattr(warmup, "warm_theme_caches", _noop)
    with TestClient(server.app) as c:
        yield c


@pytest.fixture
def at_time(monkeypatch):
    """save_review·save_solved_problem 이 기록하는 created_at·imported_at 을 고정 시각으로 강제한다.

    created_at 은 datetime.now() 로 찍히므로 연속 저장의 순서(→ 최신 판정)를 결정론적으로
    제어하려면 필요하다. ISO 문자열은 사전순=시간순이므로 정렬 의미가 보존된다.
    """
    def _apply(iso: str):
        fixed = datetime.fromisoformat(iso)

        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed if tz is None else fixed.replace(tzinfo=tz)

        monkeypatch.setattr("db.reviews.datetime", _Frozen)
        monkeypatch.setattr("db.solved.datetime", _Frozen)

    return _apply
