"""add reviews.language

Revision ID: c4d9a1f70b32
Revises: b1e7ca113c96
Create Date: 2026-08-14 10:00:00.000000

리뷰 대기 상태로 올린 풀이를 나중에 재리뷰·재업로드할 때 같은 파일명(확장자)을 재현하려면
제출 언어가 필요하다. 기존 행은 빈 문자열이 되고, 확장자 폴백은 clients._get_file_extension 이 처리한다.

alembic_version 이 없던 기존 DB 는 baseline 부터 다시 실행되므로 컬럼이 이미 있을 수 있다 —
baseline 의 if_not_exists 와 같은 정신으로 존재 여부를 확인하고 방어한다(SQLite 는
ADD COLUMN IF NOT EXISTS 를 지원하지 않는다).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'c4d9a1f70b32'
down_revision: str | None = 'b1e7ca113c96'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_language_column() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns('reviews')
    return any(column["name"] == "language" for column in columns)


def upgrade() -> None:
    if not _has_language_column():
        op.add_column('reviews',
                      sa.Column('language', sa.Text(), server_default=sa.text("('')"),
                                nullable=False))


def downgrade() -> None:
    if _has_language_column():
        op.drop_column('reviews', 'language')
