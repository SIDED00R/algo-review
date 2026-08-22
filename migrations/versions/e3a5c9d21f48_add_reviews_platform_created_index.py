"""add idx_reviews_platform_created

Revision ID: e3a5c9d21f48
Revises: d7f2b45c81a3
Create Date: 2026-08-22 15:00:00.000000

`get_review_history` 는 `WHERE platform=? ORDER BY created_at DESC LIMIT 20` 인데,
기존 인덱스는 `platform` 단독과 `created_at` 단독뿐이라 옵티마이저가 platform 인덱스로
행을 고른 뒤 **전부 임시 B-트리에 넣어 정렬**한다(EXPLAIN: USE TEMP B-TREE FOR ORDER BY).
20행을 얻으려고 그 플랫폼의 전 행을 정렬하는 셈이다.

실측(reviews 5만 행, sqlite): 210ms → 0.1ms. `/api/stats` 와 `/api/report` 가 둘 다
이 함수를 쓴다. Postgres 도 같은 인덱스 집합이라 동일하게 적용된다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'e3a5c9d21f48'
down_revision: str | None = 'd7f2b45c81a3'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_INDEX = "idx_reviews_platform_created"


def _has_index() -> bool:
    names = {ix["name"] for ix in sa.inspect(op.get_bind()).get_indexes("reviews")}
    return _INDEX in names


def upgrade() -> None:
    # 이 리비전을 두 인스턴스가 동시에 올릴 수 있다 — 존재 확인으로 방어한다
    # (baseline 의 if_not_exists 와 같은 정신).
    if not _has_index():
        op.create_index(_INDEX, "reviews", ["platform", "created_at"])


def downgrade() -> None:
    if _has_index():
        op.drop_index(_INDEX, table_name="reviews")
