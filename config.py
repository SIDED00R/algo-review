"""중앙 설정 — 환경변수를 읽어 SQLAlchemy 접속 URL 을 조립한다."""
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import URL


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # --- 데이터베이스 ---
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

    # --- OpenAI (또는 OpenAI 호환 엔드포인트) ---
    openai_api_key: str = ""
    # OpenAI 호환 엔드포인트를 제공하는 다른 제공자(예: Gemini)로 갈아끼울 때 지정한다.
    # 비워 두면 OpenAI 기본 엔드포인트를 쓴다 — 되돌리려면 이 값만 지우면 된다.
    openai_base_url: str | None = None
    # model / max_tokens 는 리뷰(analyzer)와 번역(cf_translator)의 기본값이 다르므로
    # None 으로 두고 각 호출부에서 폴백한다(env 설정 시 양쪽 모두 그 값을 쓴다).
    openai_model: str | None = None
    openai_max_tokens: int | None = None
    openai_report_max_tokens: int = 1024
    openai_temperature: float = 0.3
    # 재시도는 타임아웃과 곱해져 실효 상한을 만든다 — 둘을 함께 조절할 수 있어야 한다.
    openai_max_retries: int = 1
    openai_timeout: int = 15

    # --- GitHub OAuth ---
    github_client_id: str = ""
    github_client_secret: str = ""
    app_url: str = "http://localhost:8080"

    # --- Codeforces ---
    codeforces_api_key: str | None = None
    codeforces_api_secret: str | None = None

    # --- 기타 ---
    compile_timeout: int = 30
    cors_origins: str = "http://localhost:8080"
    demo_mode: bool = False
    # 임의 코드 실행(/api/execute)은 기본으로 닫는다 — 자식 프로세스가 앱과 같은 uid·같은
    # 네트워크 네임스페이스에서 돌아 인프로세스 하드닝으로는 안전해지지 않는다.
    # 로컬 개발에서만 EXECUTE_ENABLED=true 로 켠다.
    execute_enabled: bool = False

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
