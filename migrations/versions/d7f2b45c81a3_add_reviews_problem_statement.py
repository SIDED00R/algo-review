"""add reviews.problem_statement

Revision ID: d7f2b45c81a3
Revises: c4d9a1f70b32
Create Date: 2026-08-21 20:00:00.000000

'지난 제출 불러오기' 로 리뷰 폼을 복원할 때 문제 설명 칸도 채워야 한다. 담는 값은
사용자가 textarea 에 붙여 넣은 원문뿐이다 — 서버가 스크래핑해 LLM 에 넘긴 본문은
재제출 시 resolve_statement 가 다시 해석하므로 저장할 이유가 없다.

이 칸을 비우지 않으면 조용한 오답이 난다: resolve_statement 는 요청에 본문이 있으면
무조건 그것을 쓰므로, 이전 문제의 붙여넣은 본문이 남아 있으면 다른 문제를 그 본문으로
리뷰한다. 그래서 로더는 값이 없어도 빈 문자열을 대입한다.

alembic_version 이 없던 기존 DB 는 baseline 부터 다시 실행되므로 컬럼이 이미 있을 수 있다 —
baseline 의 if_not_exists 와 같은 정신으로 존재 여부를 확인하고 방어한다(SQLite 는
ADD COLUMN IF NOT EXISTS 를 지원하지 않는다).
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'd7f2b45c81a3'
down_revision: str | None = 'c4d9a1f70b32'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _has_problem_statement_column() -> bool:
    columns = sa.inspect(op.get_bind()).get_columns('reviews')
    return any(column["name"] == "problem_statement" for column in columns)


def upgrade() -> None:
    if not _has_problem_statement_column():
        op.add_column('reviews',
                      sa.Column('problem_statement', sa.Text(), server_default=sa.text("('')"),
                                nullable=False))


def downgrade() -> None:
    if _has_problem_statement_column():
        # batch 모드로 감싼다 — 구 SQLite(3.35 미만)는 DROP COLUMN 을 지원하지 않는다.
        with op.batch_alter_table('reviews') as batch_op:
            batch_op.drop_column('problem_statement')
