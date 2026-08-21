"""Alembic 마이그레이션 자체 검증 — 세 가지 DB 상태가 upgrade head 로 수렴하는지 확인한다."""
from sqlalchemy import inspect, text

import db
from db.connection import dispose_engine, get_engine, session_scope

_EXPECTED_TABLES = {"reviews", "tag_stats", "solved_history", "github_settings", "api_cache"}


def _table_names():
    return set(inspect(get_engine()).get_table_names())


def test_migration_creates_all_tables():
    # fresh_db 픽스처가 이미 run_migrations 를 돌렸다.
    assert _EXPECTED_TABLES <= _table_names()
    assert "alembic_version" in _table_names()


def test_migration_is_idempotent():
    db.run_migrations()  # 두 번째 실행이 실패 없이 no-op
    assert _EXPECTED_TABLES <= _table_names()


def test_legacy_db_without_alembic_version_converges(tmp_path, monkeypatch):
    """alembic_version 없이 일부 테이블만 있는 기존 DB 가 upgrade 로 나머지 테이블 + stamp 를 얻는다.

    실제 로컬 DB 상태(완전한 4개 테이블 + api_cache 누락 + alembic_version 없음)를 재현한다.
    """
    legacy = tmp_path / "legacy.db"
    monkeypatch.setenv("DB_PATH", str(legacy))
    dispose_engine()

    # 완전한 스키마를 만든 뒤, 최신 테이블(api_cache)과 stamp 를 제거해 pre-alembic 상태로 되돌린다.
    db.run_migrations()
    with session_scope(commit=True) as session:
        session.execute(text("DROP TABLE api_cache"))
        session.execute(text("DROP TABLE alembic_version"))
    dispose_engine()
    assert "api_cache" not in _table_names()
    assert "alembic_version" not in _table_names()

    db.run_migrations()

    names = _table_names()
    assert "api_cache" in names          # 누락됐던 테이블이 재생성됨
    assert "alembic_version" in names     # stamp 됨
    # baseline 이후 리비전도 이미 반영된 상태를 덮어쓰지 않고 통과해야 한다.
    columns = {c["name"] for c in inspect(get_engine()).get_columns("reviews")}
    assert "language" in columns
    assert "problem_statement" in columns
    dispose_engine()
