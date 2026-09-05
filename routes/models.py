import re

from pydantic import BaseModel, Field, field_validator

from constants import is_supported_platform, normalize_platform


MAX_CODE_LENGTH = 50_000
MAX_STATEMENT_LENGTH = 100_000
# 저장소 경로 세그먼트·커밋 메시지·README 헤더로 나가는 값들. GitHub 경로 상한(255바이트/
# 세그먼트)과 사람이 읽을 수 있는 길이를 함께 고려한 값이다.
MAX_TITLE_LENGTH = 200
MAX_TAGS = 30
MAX_TAG_LENGTH = 100
MAX_URL_LENGTH = 500


def validate_code_length(value: str) -> str:
    """제출 코드 길이 상한. 리뷰 요청과 저장소 push 요청이 같은 상한을 쓴다."""
    if len(value) > MAX_CODE_LENGTH:
        raise ValueError(f"코드는 {MAX_CODE_LENGTH:,}자를 초과할 수 없습니다.")
    return value


def validate_statement_length(value: str | None) -> str | None:
    """문제 본문 길이 상한. 프롬프트와 저장소 README 양쪽으로 흘러간다."""
    if value is not None and len(value) > MAX_STATEMENT_LENGTH:
        raise ValueError(f"문제 설명은 {MAX_STATEMENT_LENGTH:,}자를 초과할 수 없습니다.")
    return value


def validate_platform(value: str) -> str:
    """플랫폼 문자열을 정규화·검증한다. 지원하지 않으면 ValueError.

    pydantic validator 가 직접 쓰는 형태다. 라우터는 이것을 감싸 400 으로 바꾸는
    `routes.helpers.require_platform` 을 쓴다.
    """
    platform = normalize_platform(value)
    if not is_supported_platform(platform):
        raise ValueError("지원하지 않는 플랫폼입니다. 'boj' 또는 'codeforces'만 가능합니다.")
    return platform


class ReviewRequest(BaseModel):
    platform: str = "boj"
    # gt=0 — 프론트의 `if (!problemId)` 가드는 문자열 "0" 을 통과시키므로(!"0" === false)
    # 이 하한이 없으면 problem_id=0 이 서버까지 도달해 "문제 0" 리뷰 행이 저장된다.
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
        return validate_code_length(v)

    @field_validator("problem_statement")
    @classmethod
    def statement_max_length(cls, v):
        return validate_statement_length(v)


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

    # /api/push-review 는 인증이 없고 값이 그대로 저장소에 커밋된다 — 리뷰 경로와 같은
    # 상한을 둔다. 여기에만 상한이 없으면 50,000자 게이트가 이 경로로 우회된다.
    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        return validate_code_length(v)

    # title·tier_name 은 저장소 **경로 세그먼트**가 되고, tags·url 은 README 본문이 된다.
    # 상한이 없으면 요청 1건으로 수 MB 파일을 커밋하거나 경로 길이 한계를 넘길 수 있다.
    @field_validator("title", "tier_name", "language")
    @classmethod
    def short_text_fields(cls, v):
        if len(v or "") > MAX_TITLE_LENGTH:
            raise ValueError(f"{MAX_TITLE_LENGTH}자를 초과할 수 없습니다.")
        return v

    @field_validator("url")
    @classmethod
    def url_bounds(cls, v):
        value = (v or "").strip()
        if not value:
            return value
        if len(value) > MAX_URL_LENGTH:
            raise ValueError(f"URL 은 {MAX_URL_LENGTH}자를 초과할 수 없습니다.")
        # README 의 링크가 되는 값이다 — 프론트 problemUrl 과 같은 허용목록을 쓴다.
        if not re.match(r"^https?://", value, re.I):
            raise ValueError("문제 링크는 http(s) 주소여야 합니다.")
        return value

    @field_validator("tags")
    @classmethod
    def tag_bounds(cls, v):
        tags = v or []
        if len(tags) > MAX_TAGS:
            raise ValueError(f"태그는 {MAX_TAGS}개를 초과할 수 없습니다.")
        for tag in tags:
            if len(tag) > MAX_TAG_LENGTH:
                raise ValueError(f"태그는 {MAX_TAG_LENGTH}자를 초과할 수 없습니다.")
        return tags

    @field_validator("description", "input_desc", "output_desc")
    @classmethod
    def statement_max_length(cls, v):
        return validate_statement_length(v)


class ExecuteRequest(BaseModel):
    code: str
    language: str = "python3"
    stdin: str = ""
    timeout_sec: int = 5

    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        return validate_code_length(v)

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


class DraftSaveRequest(BaseModel):
    """에디터 임시 저장 요청. 코드가 비면 저장 대신 그 임시 저장본을 지운다(db.save_draft)."""
    code: str
    # 복원할 때 되돌릴 언어 선택 값이다 — select 의 option value 라 짧다.
    language: str = Field(default="", max_length=50)

    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        return validate_code_length(v)


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
