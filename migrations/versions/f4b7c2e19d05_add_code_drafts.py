"""add code_drafts

Revision ID: f4b7c2e19d05
Revises: e3a5c9d21f48
Create Date: 2026-09-02 10:00:00.000000

에디터 임시 저장본을 담는 표. 키 하나가 에디터 자리 하나다(메인 리뷰 탭 `main`,
문제 뷰어 `codeforces:{ref}`).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'f4b7c2e19d05'
down_revision: str | None = 'e3a5c9d21f48'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # 인스턴스 두 개가 동시에 올릴 수 있다 — baseline 과 같은 정신으로 방어한다.
    op.create_table('code_drafts',
    sa.Column('draft_key', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('language', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('draft_key'),
    if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table('code_drafts', if_exists=True)
