from pydantic import BaseModel, Field, field_validator

from constants import is_supported_platform, normalize_platform


def validate_platform(value: str) -> str:
    """pydantic 검증용 — 패키지 밖 3개 모듈이 쓰므로 이름에 밑줄을 두지 않는다."""
    platform = normalize_platform(value)
    if not is_supported_platform(platform):
        raise ValueError("지원하지 않는 플랫폼입니다. 'boj' 또는 'codeforces'만 가능합니다.")
    return platform


class ReviewRequest(BaseModel):
    platform: str = "boj"
    # gt=0 — 프론트의 `if (!problemId)` 가드는 문자열 "0" 을 통과시키므로(!"0" === false)
    # problem_id=0 이 서버까지 도달해 "문제 0" 리뷰 행이 저장됐다.
    problem_id: int | None = Field(default=None, gt=0)
    problem_ref: str | None = None
    problem_statement: str | None = None
    code: str
    # 저장소 파일 확장자에 쓰인다 — 나중에 재업로드할 때 같은 파일명을 재현하려면 기록해 두어야 한다.
    language: str = ""

    @field_validator("platform")
    @classmethod
    def _validate_platform(cls, v):
        return validate_platform(v)

    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        if len(v) > 50_000:
            raise ValueError("코드는 50,000자를 초과할 수 없습니다.")
        return v


class ImportRequest(BaseModel):
    boj_id: str
    session_cookie: str | None = None
    max_pages: int = 5

    @field_validator("boj_id")
    @classmethod
    def boj_id_required(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("BOJ 아이디를 입력해주세요.")
        return value

    @field_validator("max_pages")
    @classmethod
    def max_pages_bounds(cls, v):
        # 9999("전체") 선택 시 모든 기록을 가져온다 — 무한 루프 방지용 안전 상한만 둔다.
        # get_user_submissions가 더 가져올 기록이 없으면 자동으로 멈추므로 이 상한은 거의 도달하지 않는다.
        return max(1, min(v, 1000))


class GithubImportRequest(BaseModel):
    repo: str
    token: str | None = None

    @field_validator("repo")
    @classmethod
    def github_repo_format(cls, v):
        repo = (v or "").strip()
        if not repo or "/" not in repo:
            raise ValueError("저장소를 owner/repo 형식으로 입력해주세요.")
        return repo


class CodeforcesImportRequest(BaseModel):
    handle: str
    count: int = 200
    api_key: str | None = None
    api_secret: str | None = None
    github_repo: str | None = None
    github_token: str | None = None

    @field_validator("handle")
    @classmethod
    def handle_required(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("Codeforces handle을 입력해주세요.")
        return value

    @field_validator("count")
    @classmethod
    def count_bounds(cls, v):
        return max(1, min(v, 1000))


class SetRepoRequest(BaseModel):
    repo: str

    @field_validator("repo")
    @classmethod
    def target_repo_format(cls, v):
        repo = (v or "").strip()
        if not repo or "/" not in repo:
            raise ValueError("저장소를 owner/repo 형식으로 입력해주세요.")
        return repo


class PushReviewRequest(BaseModel):
    platform: str
    problem_ref: str
    title: str
    tier_name: str
    tags: list[str] = Field(default_factory=list)
    code: str
    language: str = ""
    url: str = ""
    description: str = ""
    input_desc: str = ""
    output_desc: str = ""

    @field_validator("platform")
    @classmethod
    def _validate_platform(cls, v):
        return validate_platform(v)

    @field_validator("problem_ref", "title", "code")
    @classmethod
    def required_text_fields(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("필수 입력값이 비어 있습니다.")
        return value


class ExecuteRequest(BaseModel):
    code: str
    language: str = "python3"
    stdin: str = ""
    timeout_sec: int = 5

    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        if len(v) > 50_000:
            raise ValueError("코드는 50,000자를 초과할 수 없습니다.")
        return v

    @field_validator("stdin")
    @classmethod
    def stdin_max_length(cls, v):
        if len(v) > 10_000:
            raise ValueError("입력은 10,000자를 초과할 수 없습니다.")
        return v

    @field_validator("timeout_sec")
    @classmethod
    def timeout_bounds(cls, v):
        return max(1, min(v, 10))


class ReviewResponse(BaseModel):
    problem_id: int
    platform: str
    problem_ref: str
    problem_url: str
    title: str
    tier: int
    tier_name: str
    tags: list[str]
    efficiency: str
    complexity: str
    better_algorithm: str | None
    feedback: str
    strengths: list[str]
    weaknesses: list[str]
