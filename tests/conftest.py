"""테스트 픽스처.

방언은 프로세스 단위로 고정된다 — db.connection.USE_POSTGRES 가 import 시점 상수라
한 테스트 실행 안에서 sqlite/postgres 를 섞을 수 없다. CI 는 dialect 매트릭스로
같은 스위트를 두 방언에 각각 돌린다(.github/workflows/deploy.yml).

- sqlite(기본): 테스트마다 tmp 파일 DB 를 새로 만든다.
- postgres(CI, DB_TYPE=postgres): 세션 전체가 한 DB 를 공유하고 테스트마다 테이블을 비운다.
"""
from datetime import datetime

import pytest

import db
from db.connection import USE_POSTGRES, db_cursor

_TABLES = ["reviews", "tag_stats", "solved_history", "github_settings", "api_cache"]


def _truncate_all():
    with db_cursor(commit=True) as cur:
        for table in _TABLES:
            cur.execute(f"DELETE FROM {table}")


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    if USE_POSTGRES:
        db.init_db()
        _truncate_all()
        yield
        _truncate_all()
    else:
        monkeypatch.setenv("DB_PATH", str(tmp_path / "test.db"))
        db.init_db()
        yield


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
