"""프로그래매틱 Alembic 마이그레이션 실행."""
import logging
from pathlib import Path

from alembic import command
from alembic.config import Config

logger = logging.getLogger("uvicorn.error")

_ROOT = Path(__file__).parent.parent


def run_migrations():
    """스키마를 head 리비전까지 올린다. 앱 기동·데모 시드·테스트에서 호출한다."""
    cfg = Config(str(_ROOT / "alembic.ini"))
    # 프로그래매틱 실행은 CWD 와 무관하게 절대경로로 고정한다.
    cfg.set_main_option("script_location", str(_ROOT / "migrations"))
    command.upgrade(cfg, "head")
    logger.info("DB migrated to head")
