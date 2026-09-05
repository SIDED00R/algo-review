"""테스트 픽스처.

방언은 프로세스 단위로 고정된다 — 한 테스트 실행 안에서 sqlite/postgres 를 섞지 않는다.
CI 는 dialect 매트릭스로 같은 스위트를 두 방언에 각각 돌린다(.github/workflows/deploy.yml).

- sqlite(기본): 테스트마다 tmp 파일 DB 를 새로 만들고 엔진을 리셋한다.
- postgres(CI, DB_TYPE=postgres): 세션 전체가 한 DB 를 공유하고 테스트마다 테이블을 비운다.

in-memory sqlite 는 쓰지 않는다 — alembic 이 별도 커넥션으로 붙으면 스키마가 사라진다.
"""
import pathlib
from datetime import datetime

import pytest
from sqlalchemy import make_url, text

import db
from config import Settings
from db.connection import dispose_engine, session_scope

# 모델에서 유도한다 — 손으로 적으면 새 테이블을 목록에 넣지 않아도 아무것도 실패하지 않고,
# postgres 다리에서 그 테이블만 비워지지 않아 테스트 간 조용한 오염이 생긴다.
TABLES = [t.name for t in db.models.Base.metadata.sorted_tables]
_REPO_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _resolved_url():
    """앱이 실제로 붙을 URL. Settings 는 os.environ 뿐 아니라 .env 도 읽는다."""
    return make_url(str(Settings().sqlalchemy_url))


# 해석된 URL 에서 방언을 판정한다. os.environ["DB_TYPE"] 을 보면 안 된다 —
# config.sqlalchemy_url 은 DATABASE_URL 을 최우선으로 쓰고 그 값은 .env 에서도 온다.
IS_POSTGRES = _resolved_url().get_backend_name().startswith("postgresql")

# IS_DEMO 는 모듈 import 시점에 한 번 결정된다 — 환경의 DEMO_MODE=true 가 비-데모를
# 전제한 테스트를 깨뜨린다. 전제를 코드에 못박고, 데모 테스트는 각자 True 로 되돌린다.
_DEMO_AWARE_MODULES = [
    # server 도 넣는다 — client 픽스처가 lifespan 을 실제로 태우므로, 빠뜨리면
    # DEMO_MODE=true 환경에서 demo_seed.seed() 가 테스트 DB 에 행을 심고 마이그레이션이
    # 스킵된다.
    "server",
    "routes.auth", "routes.execute", "routes.github_push",
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
def isolated_execute_route(monkeypatch):
    """실행 위임 설정과 레이트리밋 상태를 테스트마다 초기화한다.

    - `EXECUTOR_URL` 이 개발자 `.env` 에 있으면 테스트가 실제 실행 서비스를 호출한다.
      위임 경로를 보는 테스트는 스스로 URL 을 넣는다.
    - 레이트리밋 카운터는 프로세스 전역이고 TestClient 는 모두 같은 IP 라, 초기화하지
      않으면 스위트 뒷부분의 /api/execute 테스트가 429 로 떨어진다.
    """
    from routes import execute as execute_route
    monkeypatch.setattr(execute_route.settings, "executor_url", None)
    monkeypatch.setattr(execute_route, "_recent_calls", {})
    monkeypatch.setattr(execute_route, "_global_calls", [])


def _assert_disposable_target(url):
    """이 DB 를 마이그레이션하고 지워도 되는지 확인한다.

    스위트는 DROP TABLE·전 테이블 DELETE 를 수행한다. 격리가 어긋나면 실DB 가 대상이
    되므로, 조용히 진행하지 않고 즉시 멈춘다.

    sqlite 는 **리포 밖**이면서 파일명이 정확히 `test.db` 이거나 경로에 `pytest` 세그먼트가
    있는 것만 허용한다. `"test" in name` 같은 부분일치는 `latest.db`·`contest.db`·
    `protest.db` 를 통과시킨다 — 개발자가 `.env` 에
    `DATABASE_URL=sqlite:///.../contest.db` 를 두면 그 파일이 DROP 대상이 된다.
    """
    backend = url.get_backend_name()
    if backend.startswith("sqlite"):
        database = url.database or ""
        path = pathlib.Path(database).resolve() if database else None
        disposable = path is not None and (path.name == "test.db" or "pytest" in path.parts)
        in_repo = path is not None and path.is_relative_to(_REPO_ROOT)
        if disposable and not in_repo:
            return
        raise RuntimeError(
            f"테스트가 임시 sqlite 파일이 아닌 DB 를 가리킵니다: {database} — "
            ".env 의 DATABASE_URL·DB_PATH 가 격리를 덮고 있는지 확인하세요.")
    if backend.startswith("postgresql"):
        host = (url.query.get("host") or url.host or "")
        if url.database in ("test", "postgres") and host in ("localhost", "127.0.0.1", ""):
            return
        raise RuntimeError(
            f"테스트가 로컬 CI 용이 아닌 postgres 를 가리킵니다: {url.render_as_string(hide_password=True)} — "
            "스위트는 DROP TABLE 을 수행합니다 — 중단합니다.")
    raise RuntimeError(f"지원하지 않는 테스트 대상 방언입니다: {backend}")


@pytest.fixture(autouse=True)
def clean_process_caches():
    """프로세스 수명 캐시를 테스트마다 비운다.

    DB 는 테스트마다 갈아끼우는데 이 값들은 모듈 전역이라 남는다 — 앞 테스트가 심은
    상태가 뒤 테스트의 판정을 바꾼다.
    """
    from clients import codeforces, solved_ac

    db.reset_tag_stats_rebuild_flag()
    solved_ac._TAG_KEY_CACHE.clear()
    solved_ac._TAG_KEY_FALLBACK.clear()
    codeforces._snapshot = None
    codeforces._lookup = None
    codeforces._last_force_refresh = 0.0
    yield


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    if IS_POSTGRES:
        _assert_disposable_target(_resolved_url())
        dispose_engine()
        db.run_migrations()
        _truncate_all()
        yield
        _truncate_all()
    else:
        # DATABASE_URL 을 **지우지 않고 덮어쓴다**. pydantic-settings 의 우선순위는
        # init > OS 환경변수 > dotenv 라, `delenv` 는 OS 환경변수만 지우고 `.env` 의
        # 값을 그대로 되살린다(그러면 DB_PATH 가 무시되고 그 DB 에 붙는다).
        monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'test.db').as_posix()}")
        monkeypatch.setenv("DB_TYPE", "sqlite")
        monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
        _assert_disposable_target(_resolved_url())
        dispose_engine()
        db.run_migrations()
        yield
        dispose_engine()


@pytest.fixture
def minimal_app():
    """라우터만 얹은 최소 앱 팩토리 — `client` 와 **다른 것**임을 이름으로 구분한다.

    아래 `client` 는 server.app 전체라 전역 예외 핸들러가 걸려 있다(OperationalError
    → 503, 미처리 예외 → 500 + 고정 문구). 최소 앱에는 그것이 없다. 두 픽스처가 같은
    이름이면 테스트 본문만 보고는 어느 쪽인지 알 수 없다.
    """
    from fastapi import FastAPI
    from fastapi.testclient import TestClient

    def _make(*routers, **kwargs):
        app = FastAPI()
        for router in routers:
            app.include_router(router)
        return TestClient(app, **kwargs)

    return _make


@pytest.fixture
def client(monkeypatch):
    """server.app 전체를 얹은 TestClient. lifespan 의 warmup 백그라운드 태스크(외부 API)를
    no-op 으로 막는다."""
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

    created_at 은 현재 시각으로 찍히므로 연속 저장의 순서(→ 최신 판정)를 결정론적으로
    제어하려면 필요하다. ISO 문자열은 사전순=시간순이므로 정렬 의미가 보존된다.

    두 저장 경로가 timestamps.utc_now_iso() 하나를 쓰므로 고정할 지점도 하나다.
    인자로 받는 iso 는 **UTC 벽시계**다(운영의 Cloud Run 컨테이너와 같다).
    """
    def _apply(iso: str):
        fixed = datetime.fromisoformat(iso)

        class _Frozen(datetime):
            @classmethod
            def now(cls, tz=None):
                return fixed if tz is None else fixed.replace(tzinfo=tz)

        monkeypatch.setattr("timestamps.datetime", _Frozen)

    return _apply
