"""'예제 실행' 엔드포인트.

실행 자체는 하지 않고 격리된 실행 전용 서비스(`EXECUTOR_URL`)로 위임한다. 앱 프로세스
옆에서 임의 코드를 돌리면 자식이 앱과 같은 uid·같은 네트워크 네임스페이스에 있어
메타데이터 서버(→ SA 토큰)와 `/proc/1/environ`(→ 앱 환경변수 전체)에 도달한다.

`EXECUTOR_URL` 이 없으면 403 이다.
"""
import logging
import threading
import time

import requests
from fastapi import APIRouter, HTTPException, Request

from config import settings
from demo_mode import IS_DEMO, demo_block
from routes.models import ExecuteRequest

router = APIRouter()
logger = logging.getLogger("uvicorn.error")

_METADATA_IDENTITY_URL = (
    "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/identity"
)
# ID 토큰 수명은 1시간이다. 만료 판정을 JWT 파싱에 맡기지 않고 넉넉히 짧게 잡아 재발급한다.
_TOKEN_TTL_SEC = 1800
_token_lock = threading.Lock()
# (audience, 토큰, 만료 시각). audience 를 함께 들고 있어야 설정이 바뀌었을 때 옛 대상의
# 토큰을 새 대상에 보내지 않는다 — 그 경우 실행 서비스가 401 을 준다.
_cached_token: tuple[str, str, float] | None = None

# 이 엔드포인트에는 사용자 인증이 없다 — 남용을 IP 단위로만 막을 수 있다.
# 실행 서비스의 max-instances 가 비용 상한이고, 이쪽은 한 명이 그 상한을 독점하지
# 못하게 하는 몫이다.
_RATE_LIMIT_PER_MINUTE = 30
_GLOBAL_LIMIT = 120        # 분당 전체 실행 상한 — 키를 위조해도 이 값을 넘지 못한다
_MAX_BUCKETS = 4096        # 버킷 수 상한 — _GLOBAL_LIMIT 이 이 값 이하인 동안은 도달하지 않는다
_rate_lock = threading.Lock()
# 프로세스 로컬이라 인스턴스가 둘 이상이면 상한도 인스턴스별로만 성립한다.
_recent_calls: dict[str, list[float]] = {}
_global_calls: list[float] = []


def _client_ip(request: Request) -> str:
    # Cloud Run 은 GFE 를 거치므로 request.client 는 프록시 주소다. XFF 첫 항목은 앞단이
    # 버리지 않아 요청자가 정할 수 있다 — 개별 한도용 키일 뿐 신뢰 경계가 아니다.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _enforce_rate_limit(ip: str) -> None:
    now = time.time()
    cutoff = now - 60
    with _rate_lock:
        # 조용해진 IP 는 지운다 — 지우지 않으면 dict 가 요청한 IP 수만큼 계속 자란다.
        for key in [k for k, hits in _recent_calls.items() if not hits or hits[-1] <= cutoff]:
            del _recent_calls[key]
        hits = [t for t in _recent_calls.get(ip, []) if t > cutoff]
        if len(hits) >= _RATE_LIMIT_PER_MINUTE:
            raise HTTPException(status_code=429,
                                detail="실행 요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
        # Cloud Run 은 클라이언트가 보낸 X-Forwarded-For 를 버리지 않는다 — 이 키는 요청자가 정할 수 있다.
        # 개별 한도는 프록시 뒤 사용자를 위한 것이고, 비용 상한은 아래 전역 한도가 담당한다.
        _global_calls[:] = [t for t in _global_calls if t > cutoff]
        if len(_global_calls) >= _GLOBAL_LIMIT:
            raise HTTPException(status_code=429,
                                detail="실행 요청이 너무 잦습니다. 잠시 후 다시 시도해주세요.")
        _global_calls.append(now)
        hits.append(now)
        _recent_calls[ip] = hits
        if len(_recent_calls) > _MAX_BUCKETS:
            oldest_first = sorted(_recent_calls, key=lambda k: _recent_calls[k][-1])
            for key in oldest_first[: len(_recent_calls) - _MAX_BUCKETS]:
                del _recent_calls[key]


def _identity_token(audience: str) -> str:
    """실행 서비스 호출용 ID 토큰. Cloud Run 메타데이터 서버에서 받는다."""
    global _cached_token
    now = time.time()
    with _token_lock:
        if _cached_token and _cached_token[0] == audience and _cached_token[2] > now:
            return _cached_token[1]
    response = requests.get(_METADATA_IDENTITY_URL,
                            params={"audience": audience, "format": "full"},
                            headers={"Metadata-Flavor": "Google"}, timeout=5)
    response.raise_for_status()
    token = response.text.strip()
    with _token_lock:
        _cached_token = (audience, token, now + _TOKEN_TTL_SEC)
    return token


def _delegate(base_url: str, req: ExecuteRequest) -> dict:
    payload = {"code": req.code, "language": req.language,
               "stdin": req.stdin, "timeout_sec": req.timeout_sec}
    try:
        token = _identity_token(base_url)
        response = requests.post(f"{base_url}/run", json=payload,
                                 headers={"Authorization": f"Bearer {token}"},
                                 # 실행 자체의 상한(10초)에 컴파일·콜드스타트 몫을 더한다.
                                 timeout=req.timeout_sec + 60)
    except requests.RequestException as e:
        # 예외 원문에는 요청 URL 과 토큰 헤더가 실릴 수 있다 — 타입만 로그로 보낸다.
        logger.warning("실행 서비스 호출 실패: %s", type(e).__name__)
        raise HTTPException(status_code=502,
                            detail="코드 실행 서비스에 연결할 수 없습니다.") from None
    if response.status_code == 400:
        raise HTTPException(status_code=400, detail=f"지원하지 않는 언어: {req.language}")
    if response.status_code != 200:
        logger.warning("실행 서비스가 %s 응답: %s", response.status_code, response.text[:200])
        raise HTTPException(status_code=502, detail="코드 실행 서비스가 오류를 반환했습니다.")
    try:
        return response.json()
    except ValueError:
        # 200 인데 본문이 JSON 이 아니면 앞단(프록시·GFE)이 응답을 갈아치운 것이다.
        logger.warning("실행 서비스가 JSON 이 아닌 200 을 줬다: %s", response.text[:200])
        raise HTTPException(status_code=502,
                            detail="코드 실행 서비스가 오류를 반환했습니다.") from None


@router.post("/api/execute")
def execute_code(req: ExecuteRequest, request: Request):
    # 데모는 mock 데이터만 다룬다 — 실행 서비스도 붙이지 않는다.
    if IS_DEMO:
        demo_block("코드 실행은 데모 버전에서 지원되지 않습니다.")
    _enforce_rate_limit(_client_ip(request))
    if settings.executor_url:
        return _delegate(settings.executor_url.rstrip("/"), req)
    raise HTTPException(status_code=403, detail="코드 실행이 비활성화되어 있습니다.")
