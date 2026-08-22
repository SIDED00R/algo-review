"""테스트 DB 격리 가드 자체의 판정.

이 가드가 무너지면 스위트의 DROP TABLE·전 테이블 DELETE 가 실DB 로 나간다. 가드가
통과시키는 것과 막는 것을 여기서 못박는다 — 가드에 구멍이 있어도 다른 어떤 테스트도
빨강이 되지 않기 때문이다.
"""
import pathlib
import tempfile

import pytest
from sqlalchemy import make_url

from conftest import _assert_disposable_target

_TMP = pathlib.Path(tempfile.gettempdir()).resolve()
_REPO = pathlib.Path(__file__).resolve().parent.parent


def _sqlite(path) -> str:
    return f"sqlite:///{pathlib.Path(path).as_posix()}"


@pytest.mark.parametrize("name", ["latest.db", "contest.db", "protest.db", "greatest.db",
                                  "my-tests.db", "testdata.db"])
def test_names_that_merely_contain_test_are_rejected(name):
    """`"test" in basename` 부분일치가 통과시키던 이름들.

    `.env` 에 `DATABASE_URL=sqlite:///.../contest.db` 를 둔 개발자가 pytest 를 돌리면
    그 파일이 마이그레이션·DROP 대상이 된다.
    """
    with pytest.raises(RuntimeError):
        _assert_disposable_target(make_url(_sqlite(_TMP / name)))


def test_the_temp_test_db_is_accepted():
    _assert_disposable_target(make_url(_sqlite(_TMP / "test.db")))
    _assert_disposable_target(make_url(_sqlite(_TMP / "pytest-of-me" / "pytest-1" / "test.db")))


def test_a_file_inside_the_repo_is_rejected():
    """이름이 맞아도 리포 안이면 거부한다 — 임시 디렉터리 밖은 실데이터로 본다."""
    with pytest.raises(RuntimeError):
        _assert_disposable_target(make_url(_sqlite(_REPO / "test.db")))
    with pytest.raises(RuntimeError):
        _assert_disposable_target(make_url(_sqlite(_REPO / "coding_recommend.db")))


def test_remote_postgres_is_rejected():
    with pytest.raises(RuntimeError):
        _assert_disposable_target(make_url("postgresql+psycopg2://u:p@prod-host/realdb"))
    with pytest.raises(RuntimeError):
        _assert_disposable_target(make_url("postgresql+psycopg2://u:p@localhost/realdb"))


def test_local_ci_postgres_is_accepted():
    _assert_disposable_target(make_url("postgresql+psycopg2://u:p@localhost/test"))


def test_the_sqlite_fixture_actually_points_at_the_temp_file(tmp_path):
    """`fresh_db` 가 붙은 DB 가 정말 tmp 파일인지 — dotenv 가 덮고 있지 않은지.

    pydantic-settings 우선순위는 init > OS 환경변수 > dotenv 다. `monkeypatch.delenv` 는
    OS 환경변수만 지우므로 `.env` 의 `DATABASE_URL` 이 되살아나고, 그러면 `DB_PATH` 가
    무시된 채 그 DB 에 붙는다.
    """
    from conftest import IS_POSTGRES, _resolved_url
    if IS_POSTGRES:
        pytest.skip("postgres 다리에서는 tmp 파일을 쓰지 않는다")
    url = _resolved_url()
    assert url.get_backend_name().startswith("sqlite")
    assert pathlib.Path(url.database).name == "test.db"
    _assert_disposable_target(url)
