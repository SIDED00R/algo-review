"""baseline

Revision ID: b1e7ca113c96
Revises:
Create Date: 2026-07-21 21:29:42.682690

기존 DB(운영 PostgreSQL 전체 / 로컬 SQLite 는 api_cache 누락 / 신규 빈 DB)가 전부
`upgrade head` 한 번으로 수렴하도록 모든 생성을 if_not_exists 로 방어한다.
alembic_version 이 없던 기존 DB 는 이 리비전 실행으로 stamp 된다.
"""
from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = 'b1e7ca113c96'
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table('api_cache',
    sa.Column('cache_key', sa.Text(), nullable=False),
    sa.Column('payload', sa.Text(), nullable=False),
    sa.Column('updated_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('cache_key'),
    if_not_exists=True,
    )
    op.create_table('github_settings',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('access_token', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('github_username', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('target_repo', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    if_not_exists=True,
    )
    op.create_table('reviews',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('platform', sa.Text(), server_default=sa.text("'boj'"), nullable=False),
    sa.Column('problem_ref', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('tier', sa.Integer(), nullable=False),
    sa.Column('tier_name', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('tags', sa.Text(), nullable=False),
    sa.Column('code', sa.Text(), nullable=False),
    sa.Column('feedback', sa.Text(), nullable=False),
    sa.Column('efficiency', sa.Text(), nullable=False),
    sa.Column('complexity', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('better_algorithm', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('strengths', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('weaknesses', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('created_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    if_not_exists=True,
    )
    op.create_index('idx_reviews_created_at', 'reviews', ['created_at'], unique=False, if_not_exists=True)
    op.create_index('idx_reviews_platform', 'reviews', ['platform'], unique=False, if_not_exists=True)
    op.create_index('idx_reviews_platform_ref', 'reviews', ['platform', 'problem_ref'],
                    unique=False, if_not_exists=True)

    op.create_table('solved_history',
    sa.Column('problem_id', sa.Integer(), nullable=False),
    sa.Column('platform', sa.Text(), server_default=sa.text("'boj'"), nullable=False),
    sa.Column('problem_ref', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('title', sa.Text(), nullable=False),
    sa.Column('tier', sa.Integer(), nullable=False),
    sa.Column('tier_name', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('tags', sa.Text(), server_default=sa.text("'[]'"), nullable=False),
    sa.Column('code', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('language', sa.Text(), server_default=sa.text("('')"), nullable=False),
    sa.Column('imported_at', sa.Text(), nullable=False),
    sa.PrimaryKeyConstraint('platform', 'problem_ref'),
    if_not_exists=True,
    )
    op.create_index('idx_solved_imported_at', 'solved_history', ['imported_at'],
                    unique=False, if_not_exists=True)
    op.create_index('idx_solved_platform_ref', 'solved_history', ['platform', 'problem_ref'],
                    unique=False, if_not_exists=True)

    op.create_table('tag_stats',
    sa.Column('tag', sa.Text(), nullable=False),
    sa.Column('good_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('poor_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.Column('total_count', sa.Integer(), server_default=sa.text('0'), nullable=False),
    sa.PrimaryKeyConstraint('tag'),
    if_not_exists=True,
    )


def downgrade() -> None:
    op.drop_table('tag_stats', if_exists=True)
    op.drop_index('idx_solved_platform_ref', table_name='solved_history', if_exists=True)
    op.drop_index('idx_solved_imported_at', table_name='solved_history', if_exists=True)
    op.drop_table('solved_history', if_exists=True)
    op.drop_index('idx_reviews_platform_ref', table_name='reviews', if_exists=True)
    op.drop_index('idx_reviews_platform', table_name='reviews', if_exists=True)
    op.drop_index('idx_reviews_created_at', table_name='reviews', if_exists=True)
    op.drop_table('reviews', if_exists=True)
    op.drop_table('github_settings', if_exists=True)
    op.drop_table('api_cache', if_exists=True)
