"""LeetCode 채점기 클라이언트 — 예제 실행(interpret_solution)·제출(submit)·결과 폴링.

웹사이트가 쓰는 비공개 엔드포인트라 로그인 쿠키(LEETCODE_SESSION)와 csrftoken 이 필요하다. 세션
쿠키는 요청마다 서버가 만료를 2주 뒤로 미룬 새 값을 내려 주므로, 받은 값을 api_cache 에 저장해
다음 호출에 쓴다 — 2주 안에 한 번이라도 쓰면 수동 갱신 없이 이어진다.

쿠키 값은 어떤 예외 메시지·로그에도 싣지 않는다.
"""
import json
import logging
import time

import requests
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from sqlalchemy.exc import TimeoutError as SQLTimeoutError

from clients.utils import BROWSER_USER_AGENT, UpstreamUnavailable
from config import settings

logger = logging.getLogger("uvicorn.error")

SESSION_CACHE_KEY = "lc:judge-session:v1"
# 뷰어 언어 select 값이 곧 LeetCode langSlug 다.
JUDGE_LANGUAGES = {"python3", "cpp", "mysql"}

_BASE = "https://leetcode.com"
_TIMEOUT = 30
_POLL_INTERVAL_SEC = 1.0
_POLL_TIMEOUT_SEC = 40


class LeetCodeSessionError(ValueError):
    """세션 쿠키가 없거나 만료됐다 — 라우터가 401 로 바꾼다."""


class LeetCodeRateLimited(UpstreamUnavailable):
    """LeetCode 가 429 를 줬다(연속 실행 몇 번이면 걸린다) — 라우터가 429 로 그대로 넘긴다."""


class LeetCodeChallenged(UpstreamUnavailable):
    """Cloudflare 봇 확인(403 + `cf-mitigated: challenge`, HTML 본문). 세션 문제가 아니라 자격증명 폴백을 하지 않는다."""


def split_example_cases(example_testcases: str, meta_data: str) -> list[str]:
    """exampleTestcases(인자 한 줄씩)를 케이스별 문자열로 나눈다. 인자 수는 metaData.params 개수다.

    Database 문제(metaData.database)는 한 줄이 한 케이스(테이블 JSON)다. 인자 수를 알 수 없거나
    줄 수가 맞지 않으면 전체를 한 케이스로 둔다.
    """
    text = (example_testcases or "").strip("\n")
    if not text:
        return []
    lines = text.split("\n")
    try:
        meta = json.loads(meta_data or "")
        params = 1 if meta.get("database") else len(meta["params"])
    except (ValueError, KeyError, TypeError, AttributeError):
        params = 0
    if params < 1 or len(lines) % params:
        return [text]
    return ["\n".join(lines[i:i + params]) for i in range(0, len(lines), params)]


def _credentials() -> list[tuple[str, str]]:
    """시도할 (세션, csrf) 후보. 저장된 갱신값이 먼저, 설정값이 다음 — 설정을 새로 붙였을 때 되살아나게.

    DB 를 못 읽으면(온디맨드 DB 정지) 설정값만으로 진행한다 — 채점기 호출에 DB 는 필수가 아니다.
    """
    import db  # 지연 import(clients.leetcode 와 같은 방식)
    candidates = []
    try:
        stored = db.cache_get_stale(SESSION_CACHE_KEY)
    except (OperationalError, SQLTimeoutError) as e:
        logger.warning("LeetCode 저장 세션을 읽지 못해 설정값만 쓴다: %s", type(e).__name__)
        stored = None
    if isinstance(stored, dict) and stored.get("session") and stored.get("csrf"):
        candidates.append((stored["session"], stored["csrf"]))
    env = ((settings.leetcode_session or "").strip(), (settings.leetcode_csrftoken or "").strip())
    if all(env) and env not in candidates:
        candidates.append(env)
    if not candidates:
        raise LeetCodeSessionError("LeetCode 세션이 설정되지 않았습니다. LEETCODE_SESSION·LEETCODE_CSRFTOKEN 을 넣어주세요.")
    return candidates


def _store_credentials(session: str, csrf: str) -> None:
    """갱신된 세션 저장. 부수 효과라 실패해도 호출 결과는 그대로 돌려준다 — 예외 문자열에는 바인딩 값(쿠키)이 실리므로 타입명만 남긴다."""
    import db
    try:
        db.cache_set(SESSION_CACHE_KEY, {"session": session, "csrf": csrf})
    except SQLAlchemyError as e:
        logger.warning("LeetCode 갱신 세션 저장 실패: %s", type(e).__name__)


def _client(slug: str, session: str, csrf: str) -> requests.Session:
    client = requests.Session()
    client.cookies.set("LEETCODE_SESSION", session, domain="leetcode.com")
    client.cookies.set("csrftoken", csrf, domain="leetcode.com")
    client.headers.update({
        "User-Agent": BROWSER_USER_AGENT,
        "Content-Type": "application/json",
        "Referer": f"{_BASE}/problems/{slug}/",
        "Origin": _BASE,
        "x-csrftoken": csrf,
    })
    return client


def _json_or_raise(resp: requests.Response, what: str) -> dict:
    content_type = resp.headers.get("Content-Type", "")
    if resp.headers.get("cf-mitigated") == "challenge":
        # 실측: 짧은 시간에 여러 번 부르면 인증된 요청도 이 페이지("Just a moment...")를 받는다.
        raise LeetCodeChallenged("LeetCode 의 Cloudflare 봇 확인에 막혔습니다. 잠시 후 다시 시도해주세요.")
    if resp.status_code in (401, 403):
        raise LeetCodeSessionError("LeetCode 세션이 만료됐거나 잘못됐습니다. 브라우저 쿠키를 다시 넣어주세요.")
    if resp.status_code == 429:
        raise LeetCodeRateLimited("LeetCode 가 호출을 제한했습니다. 잠시 후 다시 시도해주세요.")
    if resp.status_code >= 500:
        raise UpstreamUnavailable(f"LeetCode 채점기 오류 (HTTP {resp.status_code})")
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        # 로그인 페이지로 리다이렉트된 HTML 이 여기로 온다 — 세션이 죽은 것이다.
        if "text/html" in content_type:
            raise LeetCodeSessionError("LeetCode 세션이 만료됐거나 잘못됐습니다. 브라우저 쿠키를 다시 넣어주세요.")
        raise UpstreamUnavailable(f"LeetCode {what} 응답을 해석할 수 없습니다.")
    return payload


def _post_with_credentials(slug: str, path: str, payload: dict) -> tuple[requests.Session, dict]:
    """후보 자격증명을 차례로 시도한다. 성공하면 갱신된 세션 쿠키를 저장하고 (클라이언트, 응답) 을 준다."""
    last_error: Exception | None = None
    for session, csrf in _credentials():
        client = _client(slug, session, csrf)
        try:
            resp = client.post(f"{_BASE}{path}", data=json.dumps(payload), timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise UpstreamUnavailable(f"LeetCode 연결 실패 ({type(e).__name__})") from None
        try:
            body = _json_or_raise(resp, "채점기")
        except LeetCodeSessionError as e:
            last_error = e
            continue
        # 이 응답이 준 쿠키만 본다. 세션 항아리(client.cookies)는 우리가 넣은 `leetcode.com` 쿠키와
        # 서버가 준 `.leetcode.com` 쿠키를 따로 들고 있어 domain 으로 조회하면 옛 값이 나온다(실측).
        refreshed = resp.cookies.get("LEETCODE_SESSION")
        if refreshed and refreshed != session:
            _store_credentials(refreshed, csrf)
        return client, body
    raise last_error or LeetCodeSessionError("LeetCode 세션이 없습니다.")


def _poll(client: requests.Session, submission_id: str) -> dict:
    deadline = time.time() + _POLL_TIMEOUT_SEC
    while time.time() < deadline:
        try:
            resp = client.get(f"{_BASE}/submissions/detail/{submission_id}/check/", timeout=_TIMEOUT)
        except requests.RequestException as e:
            raise UpstreamUnavailable(f"LeetCode 연결 실패 ({type(e).__name__})") from None
        body = _json_or_raise(resp, "채점 결과")
        if body.get("state") == "SUCCESS":
            return body
        time.sleep(_POLL_INTERVAL_SEC)
    raise UpstreamUnavailable("LeetCode 채점 결과를 기다리다 시간이 초과됐습니다.")


def _error_text(body: dict) -> str:
    return (body.get("full_compile_error") or body.get("compile_error")
            or body.get("full_runtime_error") or body.get("runtime_error") or "")


def run_examples(slug: str, question_id: str, language: str, code: str, cases: list[str]) -> dict:
    """예제 실행. 제출 기록은 남지 않는다. 기대 출력은 LeetCode 가 정답 코드로 계산해 준다."""
    client, body = _post_with_credentials(slug, f"/problems/{slug}/interpret_solution/", {
        "lang": language, "question_id": question_id, "typed_code": code,
        "data_input": "\n".join(cases),
    })
    result = _poll(client, str(body["interpret_id"]))
    actual = result.get("code_answer") or []
    expected = result.get("expected_code_answer") or []
    compare = result.get("compare_result") or ""
    error = _error_text(result)
    if result.get("run_success") and len(compare) != len(cases):
        # 채점기가 본 케이스 수와 우리가 나눈 수가 다르면 판정을 짝지을 수 없다 — 틀린 것을 통과로 보이지 않게 전체를 실패로.
        error = (f"채점기는 {len(compare)}개 케이스로 판정했는데 입력은 {len(cases)}개로 나뉘었습니다. "
                 "커스텀 입력의 줄 구성을 확인해주세요.")
        result["run_success"] = False
        result["status_msg"] = "케이스 수 불일치"
    out_cases = []
    for i, case_input in enumerate(cases):
        out_cases.append({
            "input": case_input,
            "expected": expected[i] if i < len(expected) else "",
            "actual": actual[i] if i < len(actual) else "",
            "passed": bool(result.get("run_success")) and i < len(compare) and compare[i] == "1",
        })
    return {
        "status_msg": result.get("status_msg") or "",
        "run_success": bool(result.get("run_success")),
        "runtime": result.get("status_runtime") or "",
        "error": error,
        "cases": out_cases,
    }


def submit_solution(slug: str, question_id: str, language: str, code: str) -> dict:
    """실제 제출. 계정의 제출 목록에 기록이 남는다."""
    client, body = _post_with_credentials(slug, f"/problems/{slug}/submit/", {
        "lang": language, "question_id": question_id, "typed_code": code,
    })
    submission_id = str(body["submission_id"])
    url = f"{_BASE}/submissions/detail/{submission_id}/"
    try:
        result = _poll(client, submission_id)
    except (UpstreamUnavailable, LeetCodeSessionError):
        # 제출은 이미 접수됐다 — "다시 시도" 문구를 내면 중복 제출을 부른다.
        raise UpstreamUnavailable("제출은 접수됐지만 채점 결과를 받지 못했습니다. 다시 제출하지 말고 "
                                  f"제출 기록에서 확인해주세요: {url}") from None
    return {
        "submission_id": submission_id,
        "url": url,
        "status_msg": result.get("status_msg") or "",
        "accepted": result.get("status_msg") == "Accepted",
        "total_correct": result.get("total_correct"),
        "total_testcases": result.get("total_testcases"),
        "runtime": result.get("status_runtime") or "",
        "memory": result.get("status_memory") or "",
        "error": _error_text(result),
        # 오답일 때 LeetCode 가 알려 주는 첫 실패 케이스.
        "last_testcase": result.get("last_testcase") or result.get("input_formatted") or "",
        "expected_output": result.get("expected_output") or "",
        "code_output": result.get("code_output") or "",
    }
