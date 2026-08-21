"""SQLAlchemy 2.0 ORM 모델 — 운영 스키마와 컬럼·기본값·인덱스명이 일치한다.

주의:
- 날짜 컬럼(created_at/imported_at/updated_at)은 Text 로 유지한다. 기존 데이터가 ISO 문자열이고
  ISO 는 사전순=시간순이라 정렬이 유효하다. DateTime 으로 바꾸면 기존 행 파싱이 깨진다.
- tags/strengths/weaknesses 는 Text + json 문자열로 유지한다(운영 컬럼이 TEXT).
- 인덱스명은 기존과 정확히 일치시켜야 향후 autogenerate 가 drop/create 노이즈를 내지 않는다.
"""
from sqlalchemy import Index, Integer, Text, text
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Review(Base):
    __tablename__ = "reviews"

    id: Mapped[int] = mapped_column(primary_key=True)
    problem_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'boj'"))
    problem_ref: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_name: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    tags: Mapped[str] = mapped_column(Text, nullable=False)
    code: Mapped[str] = mapped_column(Text, nullable=False)
    feedback: Mapped[str] = mapped_column(Text, nullable=False)
    efficiency: Mapped[str] = mapped_column(Text, nullable=False)
    complexity: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    better_algorithm: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    strengths: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    weaknesses: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    # 불러오기로 폼을 복원할 때 쓴다. 사용자가 붙여 넣은 원문만 담는다 —
    # 서버가 스크래핑한 본문은 재제출 시 어차피 다시 해석된다(routes/problem_resolve.py).
    problem_statement: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    created_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_reviews_platform", "platform"),
        Index("idx_reviews_platform_ref", "platform", "problem_ref"),
        Index("idx_reviews_created_at", "created_at"),
    )


class TagStat(Base):
    __tablename__ = "tag_stats"

    tag: Mapped[str] = mapped_column(Text, primary_key=True)
    good_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    poor_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))
    total_count: Mapped[int] = mapped_column(Integer, nullable=False, server_default=text("0"))


class SolvedHistory(Base):
    __tablename__ = "solved_history"

    problem_id: Mapped[int] = mapped_column(Integer, nullable=False)
    platform: Mapped[str] = mapped_column(Text, primary_key=True, server_default=text("'boj'"))
    problem_ref: Mapped[str] = mapped_column(Text, primary_key=True, server_default=text("''"))
    title: Mapped[str] = mapped_column(Text, nullable=False)
    tier: Mapped[int] = mapped_column(Integer, nullable=False)
    tier_name: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    tags: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("'[]'"))
    code: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    language: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    imported_at: Mapped[str] = mapped_column(Text, nullable=False)

    __table_args__ = (
        Index("idx_solved_platform_ref", "platform", "problem_ref"),
        Index("idx_solved_imported_at", "imported_at"),
    )


class GithubSetting(Base):
    __tablename__ = "github_settings"

    id: Mapped[int] = mapped_column(primary_key=True)
    access_token: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    github_username: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))
    target_repo: Mapped[str] = mapped_column(Text, nullable=False, server_default=text("''"))


class ApiCache(Base):
    __tablename__ = "api_cache"

    cache_key: Mapped[str] = mapped_column(Text, primary_key=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(Text, nullable=False)
