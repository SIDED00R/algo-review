"""실행 전용 서비스 — 제출 코드를 돌리는 것 외에는 아무것도 하지 않는다.

앱과 분리된 Cloud Run 서비스로 배포한다. 이 이미지에는 앱 코드도, DB 접속도, 시크릿도
없고 런타임 서비스 계정에는 권한이 하나도 없다. 제출 코드가 메타데이터 서버로 토큰을
받아내거나 `/proc/1/environ` 을 읽어도 얻을 것이 없다.

호출은 앱만 할 수 있다(`--no-allow-unauthenticated` + 앱 SA 에만 run.invoker).
"""
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

from executor.runner import MAX_CODE_LENGTH, MAX_TIMEOUT_SEC, UnsupportedLanguage, run_code

app = FastAPI(title="algo-review code executor")


class RunRequest(BaseModel):
    """상한은 앱 쪽 `ExecuteRequest` 와 같은 값을 다시 건다 — 호출자를 믿지 않는다."""

    code: str
    language: str = "python3"
    stdin: str = ""
    timeout_sec: int = 5

    @field_validator("code")
    @classmethod
    def code_max_length(cls, v):
        if len(v) > MAX_CODE_LENGTH:
            raise ValueError(f"코드는 {MAX_CODE_LENGTH:,}자를 초과할 수 없습니다.")
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
        return max(1, min(v, MAX_TIMEOUT_SEC))


@app.post("/run")
def run(req: RunRequest):
    try:
        return run_code(req.language, req.code, req.stdin, req.timeout_sec)
    except UnsupportedLanguage as e:
        raise HTTPException(status_code=400, detail=str(e)) from None


@app.get("/health")
def health():
    # 경로는 /health — Cloud Run GFE 가 /healthz 를 컨테이너 전에 가로챈다.
    return {"status": "ok"}
