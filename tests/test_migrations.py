"""Alembic 마이그레이션 자체 검증 — 세 가지 DB 상태가 upgrade head 로 수렴하는지 확인한다."""
import pytest
from sqlalchemy import inspect, text

import db
from db.connection import dispose_engine, get_engine, session_scope
# conftest 를 `tests.conftest` 로 임포트하면 pytest 가 이미 top-level `conftest` 로
# 올려 둔 것과 **다른 모듈 객체**가 생긴다(Settings() 재평가 포함). 지금은 두 값이
# 결정적이라 무해하지만, conftest 에 가변 상태가 생기면 두 사본이 갈린다.
from conftest import IS_POSTGRES, TABLES

# conftest 와 같은 목록을 쓴다 — 두 곳에 적으면 테이블 추가 시 한쪽만 고쳐져
# truncate 누락으로 조용한 테스트 오염이 생긴다.
_EXPECTED_TABLES = set(TABLES)


def _table_names():
    return set(inspect(get_engine()).get_table_names())


def test_migration_creates_all_tables():
    # fresh_db 픽스처가 이미 run_migrations 를 돌렸다. 부분집합이 아니라 등가로 본다 —
    # 부분집합이면 새 모델을 추가하고 마이그레이션을 빠뜨려도 통과한다.
    assert _table_names() - {"alembic_version"} == _EXPECTED_TABLES
    assert "alembic_version" in _table_names()


def test_migration_is_idempotent():
    db.run_migrations()  # 두 번째 실행이 실패 없이 no-op
    assert _table_names() - {"alembic_version"} == _EXPECTED_TABLES


@pytest.mark.skipif(
    IS_POSTGRES,
    reason="격리 수단(DB_PATH)이 sqlite 전용이다 — config.sqlalchemy_url 은 db_type 을 먼저 "
           "보므로 postgres 다리에서는 DB_PATH 가 무시되고 세션 공유 DB 에 DROP TABLE 이 "
           "실행된다. 단정 하나가 실패하면 그 뒤 모든 테스트가 무너져 원인 추적이 어렵다.")
def test_legacy_db_without_alembic_version_converges(tmp_path, monkeypatch):
    """alembic_version 없이 일부 테이블만 있는 기존 DB 가 upgrade 로 나머지 테이블 + stamp 를 얻는다.

    실제 로컬 DB 상태(완전한 4개 테이블 + api_cache 누락 + alembic_version 없음)를 재현한다.
    sqlite 전용이다 — 위 skipif 참조.
    """
    legacy = tmp_path / "legacy.db"
    monkeypatch.setenv("DB_PATH", str(legacy))
    dispose_engine()

    try:
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
    finally:
        # 단정이 실패해도 엔진을 반드시 정리한다 — 남기면 다음 테스트가 legacy.db 를 쓴다.
        dispose_engine()
