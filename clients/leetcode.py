"""LeetCode 클라이언트 — 공개 GraphQL 로 문제 목록·본문·태그를, 로그인 세션 쿠키로 내 제출을 읽는다.

문제 식별자는 titleSlug("two-sum")다. 번호(questionFrontendId)는 스냅샷으로 slug 에 대응한다.
문제 목록 스냅샷은 questionList 를 100개씩 넘겨 받아(상한이 100 이다) 구 REST 의 풀이 수와 합친다 —
42 요청이라 프로세스 캐시 외에 api_cache 에 하루 동안 저장한다(db 는 지연 import).
"""
import logging
import re
import threading
import time

import requests
from bs4 import BeautifulSoup

from clients.utils import (BROWSER_USER_AGENT, ProblemNotFound, ProblemSearchError,
                           UpstreamUnavailable)
from constants import lc_difficulty_label

logger = logging.getLogger("uvicorn.error")

LEETCODE_GRAPHQL = "https://leetcode.com/graphql"
LEETCODE_PROBLEMS_ALL = "https://leetcode.com/api/problems/all/"
LEETCODE_HEADERS = {
    "User-Agent": BROWSER_USER_AGENT,
    "Content-Type": "application/json",
    "Referer": "https://leetcode.com",
}
_TIMEOUT = 30
_PAGE_SIZE = 100          # questionList 가 한 번에 주는 최대 개수
_REQUEST_DELAY_SEC = 0.3  # 연속 호출 사이 예절 간격

_DIFFICULTY_TIER = {"Easy": 1, "Medium": 2, "Hard": 3}

SNAPSHOT_CACHE_KEY = "lc:problemset:v1"
SNAPSHOT_TTL_SEC = 24 * 3600

# 스냅샷은 직접 관리한다(clients/codeforces.py 와 같은 규약). `_snapshot` 대입이 "준비 완료"
# 신호라 `_by_slug`·`_by_id` 를 먼저 채운 뒤 마지막에 대입한다.
_FORCE_REFRESH_COOLDOWN = 600
_last_force_refresh = 0.0
_snapshot_lock = threading.Lock()
_snapshot: list[dict] | None = None
_by_slug: dict[str, dict] | None = None
_by_id: dict[int, dict] | None = None

# slug → question(titleSlug) 응답. 리뷰 본문·README 섹션·뷰어가 같은 문제를 연달아 읽는다.
_QUESTION_CACHE_MAX = 300
_question_cache: dict[str, dict] = {}

_SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
_URL_RE = re.compile(r"^https?://(?:www\.)?leetcode\.(?:com|cn)/problems/([^/?#]+)", re.I)

# LeetCode langSlug → 앱의 언어 select 값. 없는 슬러그는 원문 그대로 둔다(확장자는 get_file_extension 이 정한다).
_LC_LANG_NAMES = {
    "cpp": "GNU C++17", "python3": "Python 3", "python": "Python 3", "java": "Java",
    "kotlin": "Kotlin", "c": "C", "csharp": "C#", "rust": "Rust", "golang": "Go",
    "javascript": "JavaScript", "typescript": "TypeScript", "swift": "Swift", "ruby": "Ruby",
    "mysql": "MySQL", "mssql": "MS SQL Server", "postgresql": "PostgreSQL", "oraclesql": "Oracle SQL",
}

_Q_LIST = (
    "query($cat:String,$limit:Int,$skip:Int,$filters:QuestionListFilterInput){"
    "questionList(categorySlug:$cat,limit:$limit,skip:$skip,filters:$filters){"
    "totalNum data{titleSlug title questionFrontendId difficulty isPaidOnly categoryTitle "
    "topicTags{name slug}}}}"
)
_Q_QUESTION = (
    "query($slug:String!){question(titleSlug:$slug){"
    "questionId questionFrontendId title titleSlug difficulty categoryTitle isPaidOnly content "
    "exampleTestcases metaData codeSnippets{langSlug code} topicTags{name slug}}}"
)
_Q_RECENT_AC = (
    "query($u:String!,$n:Int!){recentAcSubmissionList(username:$u,limit:$n){"
    "id title titleSlug timestamp lang}}"
)
_Q_STATUS = "query{userStatus{isSignedIn username}}"
_Q_SUBMISSIONS = (
    "query($offset:Int!,$limit:Int!,$lastKey:String,$slug:String!){"
    "submissionList(offset:$offset,limit:$limit,lastKey:$lastKey,questionSlug:$slug){"
    "lastKey hasNext submissions{id statusDisplay lang timestamp title titleSlug}}}"
)
_Q_SUBMISSION_DETAIL = "query($id:Int!){submissionDetails(submissionId:$id){code lang{name}}}"


def normalize_leetcode_problem_ref(problem_ref: str) -> str:
    """slug 또는 문제 URL → 소문자 slug. 번호는 여기서 받지 않는다(스냅샷이 필요하다)."""
    value = (problem_ref or "").strip()
    match = _URL_RE.match(value)
    if match:
        value = match.group(1)
    value = value.strip("/").lower()
    # slug 는 숫자만으로 이뤄지지 않는다 — 번호는 get_leetcode_problem_info 가 스냅샷으로 푼다.
    if value.isdigit() or not _SLUG_RE.match(value):
        raise ValueError("LeetCode 문제는 번호, slug, 문제 URL 로 입력해주세요. 예: 175 또는 two-sum")
    return value


def _lc_graphql(query: str, variables: dict | None = None, *, cookies: dict | None = None) -> dict:
    """GraphQL 한 번. 쿠키 값은 어떤 예외 메시지에도 싣지 않는다."""
    try:
        resp = requests.post(
            LEETCODE_GRAPHQL,
            json={"query": query, "variables": variables or {}},
            headers=LEETCODE_HEADERS,
            cookies=cookies,
            timeout=_TIMEOUT,
        )
    except requests.RequestException as e:
        raise UpstreamUnavailable(f"LeetCode API 연결 실패 ({type(e).__name__})") from None
    if resp.status_code >= 500 or resp.status_code in (403, 429):
        raise UpstreamUnavailable(f"LeetCode API 오류 (HTTP {resp.status_code})")
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        raise UpstreamUnavailable("LeetCode API 응답을 해석할 수 없습니다.")
    if payload.get("errors"):
        message = (payload["errors"][0] or {}).get("message") or "알 수 없는 오류"
        raise ValueError(f"LeetCode API 오류: {message}")
    return payload.get("data") or {}


def _snapshot_item(q: dict) -> dict | None:
    """questionList 항목 → 스냅샷 항목. 번호나 난이도가 없는 항목은 버린다."""
    try:
        problem_id = int(q.get("questionFrontendId"))
    except (TypeError, ValueError):
        return None
    tier = _DIFFICULTY_TIER.get(q.get("difficulty"))
    if not tier or not q.get("titleSlug"):
        return None
    tags = q.get("topicTags") or []
    return {
        "slug": q["titleSlug"],
        "id": problem_id,
        "title": q.get("title") or q["titleSlug"],
        "tier": tier,
        "difficulty": q["difficulty"],
        "paid": bool(q.get("isPaidOnly")),
        "category": q.get("categoryTitle") or "",
        "tags": [t.get("name", "") for t in tags if t.get("name")],
        "tag_slugs": [t.get("slug", "") for t in tags if t.get("slug")],
        "total_acs": 0,
    }


def _fetch_lc_problemset() -> list[dict]:
    """전체 문제 목록 다운로드. 페이지 하나라도 실패하면 통째로 raise — 부분 스냅샷은 설치하지 않는다."""
    items: list[dict] = []
    skip = 0
    total = None
    while total is None or skip < total:
        data = _lc_graphql(_Q_LIST, {"cat": "", "limit": _PAGE_SIZE, "skip": skip, "filters": {}})
        page = data.get("questionList") or {}
        rows = page.get("data") or []
        if total is None:
            total = int(page.get("totalNum") or 0)
        items.extend(item for item in map(_snapshot_item, rows) if item)
        if len(rows) < _PAGE_SIZE:
            break
        skip += _PAGE_SIZE
        time.sleep(_REQUEST_DELAY_SEC)
    if not items:
        raise ValueError("LeetCode 문제 목록 응답이 비어 있습니다.")

    # 풀이 수는 구 REST 에만 있다. 없으면 0 으로 두고 스냅샷은 그대로 쓴다(정렬만 무너진다).
    try:
        resp = requests.get(LEETCODE_PROBLEMS_ALL, headers=LEETCODE_HEADERS, timeout=60)
        resp.raise_for_status()
        acs = {p["stat"]["question__title_slug"]: int(p["stat"].get("total_acs") or 0)
               for p in resp.json().get("stat_status_pairs", [])}
    except Exception as e:
        logger.warning("LeetCode 풀이 수 목록 조회 실패 — 인기순 정렬 없이 진행한다: %s", e)
        acs = {}
    for item in items:
        item["total_acs"] = acs.get(item["slug"], 0)
    return items


def _install_snapshot(items: list[dict]) -> None:
    """락을 잡은 상태에서만 부른다. `_snapshot` 대입이 마지막이어야 한다."""
    global _snapshot, _by_slug, _by_id
    _by_slug = {item["slug"]: item for item in items}
    _by_id = {item["id"]: item for item in items}
    _snapshot = items


def _load_snapshot_items() -> list[dict]:
    """api_cache(하루) → 원격 → 만료 캐시 순. 전부 실패하면 raise."""
    import db  # 지연 import(스냅샷 42 요청을 인스턴스마다 반복하지 않으려고 api_cache 를 쓴다).
    cached = db.cache_get(SNAPSHOT_CACHE_KEY, SNAPSHOT_TTL_SEC)
    if cached:
        return cached
    try:
        fresh = _fetch_lc_problemset()
    except Exception as e:
        stale = db.cache_get_stale(SNAPSHOT_CACHE_KEY)
        if stale:
            logger.warning("LeetCode 문제 목록 갱신 실패 — 만료 캐시를 쓴다: %s", e)
            return stale
        raise
    db.cache_set(SNAPSHOT_CACHE_KEY, fresh)
    return fresh


def _get_lc_snapshot() -> list[dict]:
    """프로세스당 1회 받아 재사용한다. 성공 후에는 락 없는 빠른 경로다."""
    if _snapshot is not None:
        return _snapshot
    with _snapshot_lock:
        if _snapshot is None:
            _install_snapshot(_load_snapshot_items())
    return _snapshot


def _try_refresh_snapshot() -> bool:
    """스냅샷에 없는 문제를 만났을 때 1회 강제 갱신. 쿨다운 안이거나 실패하면 False."""
    global _last_force_refresh
    now = time.time()
    if not _snapshot_lock.acquire(blocking=False):
        return False
    try:
        if now - _last_force_refresh < _FORCE_REFRESH_COOLDOWN:
            return False
        _last_force_refresh = now
        try:
            fresh = _fetch_lc_problemset()
        except Exception as e:
            logger.warning("LeetCode 스냅샷 갱신 실패 — 기존 스냅샷을 유지한다: %s", e)
            return False
        import db
        db.cache_set(SNAPSHOT_CACHE_KEY, fresh)
        _install_snapshot(fresh)
        return True
    finally:
        _snapshot_lock.release()


def _lookup(ref: str) -> dict | None:
    """번호면 by_id, 아니면 slug 로 찾는다. 형식 오류는 ValueError."""
    _get_lc_snapshot()
    if ref.strip().isdigit():
        return _by_id.get(int(ref))
    return _by_slug.get(normalize_leetcode_problem_ref(ref))


def _problem_info(item: dict) -> dict:
    from clients.utils import get_problem_url
    return {
        "id": item["id"],
        "platform": "leetcode",
        "problem_ref": item["slug"],
        "title": item["title"],
        "tier": item["tier"],
        "tier_name": lc_difficulty_label(item["tier"]),
        "tags": list(item["tags"]),
        "url": get_problem_url("leetcode", item["slug"]),
    }


def get_leetcode_problem_info(problem_ref: str) -> dict:
    """번호·slug·URL 어느 형식이든 받아 문제 메타를 돌려준다. 없으면 ValueError."""
    item = _lookup(problem_ref)
    if item is None and _try_refresh_snapshot():
        item = _lookup(problem_ref)
    if item is None:
        raise ValueError(f"LeetCode 문제를 찾을 수 없습니다: {problem_ref.strip()}")
    return _problem_info(item)


def _fetch_lc_question(slug: str) -> dict | None:
    """question(titleSlug) 응답. 없는 문제는 None. 프로세스 캐시를 거친다."""
    if slug in _question_cache:
        return _question_cache[slug]
    data = _lc_graphql(_Q_QUESTION, {"slug": slug})
    question = data.get("question")
    if question is None:
        return None
    if len(_question_cache) >= _QUESTION_CACHE_MAX:
        _question_cache.pop(next(iter(_question_cache)))
    _question_cache[slug] = question
    return question


# 줄을 바꾸는 태그. 인라인 태그(code·em·sup)는 앞뒤 글자와 붙어야 "10^9"·"nums," 가 깨지지 않는다.
_BLOCK_TAGS = ("p", "div", "pre", "li", "ul", "ol", "br", "h1", "h2", "h3", "h4", "h5", "h6",
               "tr", "table", "blockquote")


def lc_html_to_text(html: str) -> str:
    """본문 HTML → LLM·README 용 텍스트. <pre>(표·예제) 줄바꿈을 지키고 <sup> 앞에 ^ 를 둔다.
    번역된 HTML 에도 그대로 쓴다(routes/problem_leetcode.py)."""
    soup = BeautifulSoup(html or "", "html.parser")
    for sup in soup.find_all("sup"):
        sup.insert_before("^")
    for tag in soup.find_all(_BLOCK_TAGS):
        tag.insert_before("\n")
        tag.insert_after("\n")
    text = soup.get_text("")
    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


_STATEMENT_FAILURE = "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 제한적으로 분석합니다."


def get_leetcode_problem_statement(problem_ref: str) -> str:
    """LLM 리뷰용 본문 텍스트. 실패·유료(content 없음)는 실패 문자열을 돌려준다(CF 와 같은 계약)."""
    try:
        question = _fetch_lc_question(normalize_leetcode_problem_ref(problem_ref))
    except Exception as e:
        logger.warning("LeetCode 문제 본문 수집 실패 (%s): %s", problem_ref, e)
        return _STATEMENT_FAILURE
    if not question or not question.get("content"):
        return _STATEMENT_FAILURE
    return lc_html_to_text(question["content"])


def get_lc_problem_sections(problem_ref: str) -> dict | None:
    """README 용 섹션. LeetCode 는 입력·출력 절이 따로 없다. 실패·유료는 None (get_cf_problem_sections 계약)."""
    text = get_leetcode_problem_statement(problem_ref)
    if text == _STATEMENT_FAILURE:
        return None
    return {"description": text, "input": "", "output": ""}


def scrape_lc_problem(problem_ref: str) -> dict:
    """뷰어용 원본. 형식 오류 ValueError, 없는 문제 ProblemNotFound. 유료 문제는 content_html 이 빈 문자열이다.

    question_id 는 채점기 호출용 내부 번호(문제 번호 problem_id 와 다르다). example_testcases 는 예제
    인자 한 줄씩, meta_data 는 함수 시그니처 JSON — clients.leetcode_judge.split_example_cases 가 쓴다.
    code_snippets 는 LeetCode langSlug → 공식 코드 스텁(에디터 초기 코드)이다."""
    from clients.utils import get_problem_url
    slug = normalize_leetcode_problem_ref(problem_ref)
    question = _fetch_lc_question(slug)
    if question is None:
        raise ProblemNotFound(f"LeetCode 에 없는 문제입니다: {slug}")
    tier = _DIFFICULTY_TIER.get(question.get("difficulty"), 0)
    return {
        "title": question.get("title") or slug,
        "problem_id": int(question.get("questionFrontendId") or 0),
        "question_id": str(question.get("questionId") or ""),
        "difficulty": question.get("difficulty") or "",
        "tier": tier,
        "category": question.get("categoryTitle") or "",
        "is_paid_only": bool(question.get("isPaidOnly")),
        "content_html": question.get("content") or "",
        "example_testcases": question.get("exampleTestcases") or "",
        "meta_data": question.get("metaData") or "",
        "code_snippets": {s["langSlug"]: s["code"]
                          for s in (question.get("codeSnippets") or []) if s.get("langSlug") and s.get("code")},
        "tags": [t.get("name", "") for t in (question.get("topicTags") or []) if t.get("name")],
        "url": get_problem_url("leetcode", slug),
    }


def search_lc_problems_by_tag(tag: str, min_tier: int, max_tier: int,
                              exclude_refs: set) -> list[dict]:
    """스냅샷 로컬 필터. tag 는 이름("Dynamic Programming")과 slug("dynamic-programming") 모두 받는다.
    유료 문제는 빼고 풀이 수 내림차순. 실패는 ProblemSearchError."""
    try:
        items = _get_lc_snapshot()
    except Exception as e:
        logger.warning("LeetCode 문제셋 스냅샷 조회 실패: %s", e)
        raise ProblemSearchError("LeetCode 문제 검색에 실패했습니다.") from e

    from clients.utils import get_problem_url
    key = (tag or "").strip().lower()
    results = []
    for item in items:
        if item["paid"] or not (min_tier <= item["tier"] <= max_tier) or item["slug"] in exclude_refs:
            continue
        if key not in item["tag_slugs"] and key not in [name.lower() for name in item["tags"]]:
            continue
        results.append({
            "id": item["slug"],
            "problem_id": item["id"],
            "title": item["title"],
            "tier": item["tier"],
            # 배지 표시 전용 짧은 라벨. 저장 경로에는 lc_difficulty_label 을 쓴다.
            "tier_name": item["difficulty"],
            "url": get_problem_url("leetcode", item["slug"]),
        })
    results.sort(key=lambda p: _by_slug[p["id"]]["total_acs"], reverse=True)
    return results


def _submission_meta(slug: str) -> dict:
    """제출 행에 붙일 문제 메타. 스냅샷에 없으면(신규 문제) question 조회로 채운다."""
    item = _by_slug.get(slug) if _by_slug else None
    if item is None:
        question = _fetch_lc_question(slug)
        if question is None:
            return {"problem_id": 0, "title": slug, "tier": 0, "tags": []}
        item = _snapshot_item(question) or {"id": 0, "title": slug, "tier": 0, "tags": []}
    return {"problem_id": item["id"], "title": item["title"], "tier": item["tier"], "tags": list(item["tags"])}


def get_leetcode_user_submissions(username: str, count: int = 20,
                                  session: str | None = None) -> list[dict]:
    """AC 제출을 문제당 최신 1건씩. 세션이 없으면 공개 API 의 최근 AC 목록(최대 20, 코드 없음)."""
    from clients.utils import get_problem_url
    username = (username or "").strip()
    if not username:
        raise ValueError("LeetCode 사용자 이름을 입력해주세요.")
    _get_lc_snapshot()

    latest: dict[str, dict] = {}   # slug → 제출(최신 순으로 처음 본 것)
    if not session:
        data = _lc_graphql(_Q_RECENT_AC, {"u": username, "n": min(max(count, 1), 20)})
        rows = data.get("recentAcSubmissionList")
        if rows is None:
            raise ValueError("LeetCode 사용자를 찾을 수 없습니다.")
        for row in rows:
            latest.setdefault(row["titleSlug"], {**row, "code": ""})
    else:
        cookies = {"LEETCODE_SESSION": session}
        status = (_lc_graphql(_Q_STATUS, cookies=cookies).get("userStatus") or {})
        if not status.get("isSignedIn"):
            raise ValueError("LEETCODE_SESSION 이 만료됐거나 잘못됐습니다. 브라우저 쿠키를 다시 넣어주세요.")
        if status.get("username", "").lower() != username.lower():
            raise ValueError(f"세션의 계정({status.get('username')})과 입력한 사용자 이름이 다릅니다.")
        offset, last_key = 0, None
        while len(latest) < count:
            data = _lc_graphql(_Q_SUBMISSIONS, {"offset": offset, "limit": 20, "lastKey": last_key, "slug": ""},
                               cookies=cookies)
            page = data.get("submissionList") or {}
            rows = page.get("submissions") or []
            for row in rows:
                if row.get("statusDisplay") == "Accepted":
                    latest.setdefault(row["titleSlug"], dict(row))
            if not page.get("hasNext") or not rows:
                break
            offset += 20
            last_key = page.get("lastKey")
            time.sleep(_REQUEST_DELAY_SEC)
        for slug, row in list(latest.items())[:count]:
            detail = _lc_graphql(_Q_SUBMISSION_DETAIL, {"id": int(row["id"])}, cookies=cookies).get("submissionDetails")
            row["code"] = (detail or {}).get("code") or ""
            time.sleep(_REQUEST_DELAY_SEC)

    submissions = []
    for slug, row in list(latest.items())[:count]:
        meta = _submission_meta(slug)
        lang_slug = row.get("lang") or ""
        submissions.append({
            "problem_ref": slug,
            "problem_id": meta["problem_id"],
            "title": meta["title"] or row.get("title") or slug,
            "tier": meta["tier"],
            "tier_name": lc_difficulty_label(meta["tier"]),
            "tags": meta["tags"],
            "language": _LC_LANG_NAMES.get(lang_slug, lang_slug),
            "code": row.get("code") or "",
            "problem_url": get_problem_url("leetcode", slug),
        })
    return submissions
