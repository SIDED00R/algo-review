from pydantic import BaseModel, Field, validator


def _normalize_platform(value: str) -> str:
    platform = (value or "boj").strip().lower()
    if platform not in {"boj", "codeforces"}:
        raise ValueError("지원하지 않는 플랫폼입니다. 'boj' 또는 'codeforces'만 가능합니다.")
    return platform


class ReviewRequest(BaseModel):
    platform: str = "boj"
    problem_id: int | None = None
    problem_ref: str | None = None
    problem_statement: str | None = None
    code: str

    _platform_validator = validator("platform", allow_reuse=True)(_normalize_platform)


class ImportRequest(BaseModel):
    boj_id: str
    session_cookie: str | None = None
    max_pages: int = 5

    @validator("boj_id")
    def boj_id_required(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("BOJ 아이디를 입력해주세요.")
        return value

    @validator("max_pages")
    def max_pages_bounds(cls, v):
        return max(1, min(v, 20))


class GithubImportRequest(BaseModel):
    repo: str
    token: str | None = None

    @validator("repo")
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

    @validator("handle")
    def handle_required(cls, v):
        value = (v or "").strip()
        if not value:
            raise ValueError("Codeforces handle을 입력해주세요.")
        return value

    @validator("count")
    def count_bounds(cls, v):
        return max(1, min(v, 1000))


class SetRepoRequest(BaseModel):
    repo: str

    @validator("repo")
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

    _platform_validator = validator("platform", allow_reuse=True)(_normalize_platform)

    @validator("problem_ref", "title", "code")
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

    @validator("code")
    def code_max_length(cls, v):
        if len(v) > 50_000:
            raise ValueError("코드는 50,000자를 초과할 수 없습니다.")
        return v

    @validator("stdin")
    def stdin_max_length(cls, v):
        if len(v) > 10_000:
            raise ValueError("입력은 10,000자를 초과할 수 없습니다.")
        return v

    @validator("timeout_sec")
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
