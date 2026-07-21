"""SQLAlchemy 엔진·세션 관리.

- 엔진은 지연(lazy) 싱글턴이다 — import 시점에 연결하지 않으므로 온디맨드 DB 가 정지 상태여도
  앱 기동을 막지 않는다(#67).
- pool_pre_ping 으로 Cloud SQL 온디맨드 재시작 후의 stale 커넥션을 자동 복구한다.
"""
from contextlib import contextmanager

from sqlalchemy import create_engine, make_url
from sqlalchemy.orm import Session

from config import Settings

_engine = None


def get_engine():
    global _engine
    if _engine is None:
        url = Settings().sqlalchemy_url  # 매 생성마다 환경변수를 새로 읽는다(테스트에서 URL 교체 가능).
        kwargs = {"pool_pre_ping": True}
        if make_url(url).get_backend_name() == "sqlite":
            # FastAPI 동기 라우트는 스레드풀에서 돌고 커넥션이 스레드를 넘나든다.
            kwargs["connect_args"] = {"check_same_thread": False}
        _engine = create_engine(url, **kwargs)
    return _engine


def dispose_engine():
    """엔진 싱글턴을 폐기한다 — 테스트에서 DB URL 을 바꿀 때 사용."""
    global _engine
    if _engine is not None:
        _engine.dispose()
        _engine = None


@contextmanager
def session_scope(commit: bool = False):
    """세션 수명을 관리한다. commit=True 면 정상 종료 시 커밋한다."""
    with Session(get_engine(), expire_on_commit=False) as session:
        yield session
        if commit:
            session.commit()
