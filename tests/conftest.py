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

_TABLES = ["reviews", "tag_stats", "solved_history", "github_settings", "api_cache"]
_IS_POSTGRES = os.environ.get("DB_TYPE", "sqlite").lower() == "postgres"


def _truncate_all():
    with session_scope(commit=True) as session:
        for table in _TABLES:
            session.execute(text(f"DELETE FROM {table}"))


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    if _IS_POSTGRES:
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
