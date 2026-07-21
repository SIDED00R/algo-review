"""중앙 설정 — 환경변수를 읽어 SQLAlchemy 접속 URL 을 조립한다.

기존 운영 Cloud Run 환경변수(DB_TYPE / DB_SOCKET / DB_NAME / DB_USER / DB_PASSWORD)를
필드명과 1:1 로 매핑하므로, 배포 시 서비스 환경변수를 바꿀 필요가 없다.
"""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # DATABASE_URL 을 직접 주면 최우선으로 사용한다(그 외 DB_* 는 무시).
    database_url: str | None = None

    db_type: str = "sqlite"          # "postgres" 면 PostgreSQL, 그 외는 SQLite
    db_socket: str | None = None     # Cloud SQL unix 소켓 경로(/cloudsql/<proj>:<region>:<inst>)
    db_name: str = "boj_review"
    db_user: str = "boj_user"
    db_password: str = ""
    db_host: str = "localhost"
    db_port: int = 5432
    db_path: str | None = None       # SQLite 파일 경로(미지정 시 리포 루트 coding_recommend.db)

    @property
    def sqlalchemy_url(self) -> URL | str:
        if self.database_url:
            return self.database_url

        if self.db_type.lower() == "postgres":
            if self.db_socket:
                # unix 소켓은 host 쿼리 파라미터로 넘긴다(psycopg2 가 소켓 디렉터리로 해석).
                return URL.create(
                    "postgresql+psycopg2",
                    username=self.db_user,
                    password=self.db_password,
                    database=self.db_name,
                    query={"host": self.db_socket},
                )
            return URL.create(
                "postgresql+psycopg2",
                username=self.db_user,
                password=self.db_password,
                host=self.db_host,
                port=self.db_port,
                database=self.db_name,
            )

        path = Path(self.db_path) if self.db_path else Path(__file__).parent / "coding_recommend.db"
        return f"sqlite:///{path.as_posix()}"


settings = Settings()
