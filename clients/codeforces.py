import logging
import re
import threading
import time
import random
import hashlib
from itertools import zip_longest
from urllib.parse import urlencode, urljoin
import requests
from bs4 import BeautifulSoup

from clients.utils import ProblemSearchError, UpstreamUnavailable

logger = logging.getLogger("uvicorn.error")

CODEFORCES_API_BASE = "https://codeforces.com/api"

CODEFORCES_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36",
    "Accept-Language": "en-US,en;q=0.9",
}

# CF 문제 페이지 본문 컨테이너 xpath — 섹션(div[2~4])과 예제(div[5]) 추출이 공용
_CF_PROBLEM_BASE_XPATH = '//*[@id="pageContent"]/div[3]/div[2]/div'


def normalize_codeforces_problem_ref(problem_ref: str) -> tuple[int, str]:
    match = re.match(r"^\s*(\d+)\s*[-/_ ]?\s*([A-Za-z][A-Za-z0-9]*)\s*$", problem_ref or "")
    if not match:
        raise ValueError("Codeforces 문제는 '4A' 또는 '4/A' 형식으로 입력해주세요.")
    contest_id = int(match.group(1))
    index = match.group(2).upper()
    return contest_id, index


def cf_rating_label(rating) -> str:
    """저장·파싱되는 CF 난이도 표준 라벨: 있으면 'Codeforces {rating}', 없으면 'Codeforces Unrated'."""
    return f"Codeforces {rating}" if rating else "Codeforces Unrated"


# problemset 전체는 수 MB · timeout 30s — 강제 갱신에 프로세스당 쿨다운을 둔다.
_FORCE_REFRESH_COOLDOWN = 600  # 10분에 1회만 강제 갱신
_last_force_refresh = 0.0

# 스냅샷은 직접 관리한다. lru_cache 는 cache_clear() 가 먼저 버리고 나중에 받으며,
# 동시 miss 를 합치지 못한다.
_snapshot_lock = threading.Lock()
_snapshot: tuple[list[dict], dict] | None = None
_lookup: dict[tuple[int, str], dict] | None = None


def get_codeforces_problem_info(problem_ref: str) -> dict:
    from clients.utils import get_problem_url
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    problem = _get_codeforces_problem_lookup().get((contest_id, index))
    if not problem:
        if _try_refresh_snapshot():
            problem = _get_codeforces_problem_lookup().get((contest_id, index))
    if not problem:
        raise ValueError(f"Codeforces 문제를 찾을 수 없습니다: {contest_id}{index}")

    rating = problem.get("rating")
    rating_label = cf_rating_label(rating)
    return {
        "id": 0,
        "platform": "codeforces",
        "problem_ref": f"{contest_id}{index}",
        "title": problem.get("name", f"Problem {contest_id}{index}"),
        "tier": 0,
        "tier_name": rating_label,
        "tags": problem.get("tags", []),
        "url": get_problem_url("codeforces", f"{contest_id}{index}"),
    }


def get_codeforces_problem_statement(problem_ref: str) -> str:
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    urls = [
        f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
        f"https://codeforces.com/contest/{contest_id}/problem/{index}",
    ]

    for url in urls:
        try:
            resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
            resp.raise_for_status()
            soup = BeautifulSoup(resp.text, "html.parser")
            statement = soup.select_one(".problem-statement")
            if statement:
                return statement.get_text(separator="\n", strip=True)
        except Exception as e:
            logger.warning("CF 문제 본문 수집 실패 (%s): %s", problem_ref, e)
            continue

    return "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 제한적으로 분석합니다."


def normalize_cf_math(text: str) -> str:
    """CF 의 수식 구분자($$$…$$$ / $$$$$$…$$$$$$)를 프론트(KaTeX)가 쓰는 $…$ / $$…$$ 로 바꾼다.

    번역 실패 시 원문이 그대로 프론트로 나가므로 번역 단계가 아니라 스크래핑 단계에서 통일한다.
    디스플레이(6달러)를 먼저 처리해야 인라인 규칙이 앞의 3달러만 먹고 짝을 어긋내지 않는다.
    """
    text = re.sub(r'\$\$\$\$\$\$(.+?)\$\$\$\$\$\$', r'$$\1$$', text, flags=re.DOTALL)
    return re.sub(r'\$\$\$(.+?)\$\$\$', r'$\1$', text, flags=re.DOTALL)


# 수식 이미지 마커의 유일한 정의. 소비처: cf_translator, tex_markers_to_markdown,
# static/js/problem-modal.js 의 restoreFormulaImages.
TEX_IMG_MARKER_RE = re.compile(r'⟦img:(https?://[^⟧\s]+)⟧')


def tex_markers_to_markdown(text: str) -> str:
    """수식 이미지 마커를 마크다운 이미지로 바꾼다 — GitHub README push 경로용."""
    return TEX_IMG_MARKER_RE.sub(r'![수식](\1)', text)


def _drop_element_keeping_tail(el, replacement: str = "") -> None:
    """el 을 트리에서 빼되 뒤따르는 텍스트(tail)는 살린다.

    lxml 의 remove() 는 el.tail 까지 함께 버리기 때문에, 그냥 지우면
    "<script>…</script>본문" 의 "본문" 같은 뒤 텍스트가 조용히 사라진다.
    """
    parent = el.getparent()
    if parent is None:
        return
    text = replacement + (el.tail or "")
    prev = el.getprevious()
    if prev is not None:
        prev.tail = (prev.tail or "") + text
    else:
        parent.text = (parent.text or "") + text
    parent.remove(el)


# KaTeX 0.16 이 유니코드로 인식하지 못하는 기호만 LaTeX 명령으로 바꾼다.
_KATEX_UNSUPPORTED = {
    "×": r"\times", "÷": r"\div", "±": r"\pm",
    "°": r"^\circ", "″": r"\prime\prime", "¬": r"\lnot",
}


def _to_katex_math(text: str) -> str:
    for char, command in _KATEX_UNSUPPORTED.items():
        text = text.replace(char, command)
    return text


def _replace_tex_spans_with_latex(el) -> None:
    """구형 문제의 <span class="tex-span"> 수식을 $…$ LaTeX 로 바꾼다.

    구형 문제는 $$$ 대신 이 마크업을 쓰는데, itertext() 로 평탄화하면
    "10<sup> - 6</sup>" 이 "10  - 6" 즉 "10 빼기 6" 으로 읽혀 의미가 뒤바뀐다.
    첨자를 ^{}/_{} 로 옮기고 전체를 $…$ 로 감싸 KaTeX 가 렌더하게 한다.
    """
    for span in el.xpath('.//span[contains(@class,"tex-span")]'):
        # 첨자를 먼저 텍스트로 접어 넣어야 아래 itertext() 에 반영된다.
        for node in span.xpath('.//sup | .//sub'):
            inner = " ".join("".join(node.itertext()).split())
            operator = "^" if node.tag == "sup" else "_"
            _drop_element_keeping_tail(node, f"{operator}{{{inner}}}" if inner else "")
        # split() 은 CF 가 즐겨 쓰는 얇은 공백(U+2009)까지 일반 공백으로 정규화한다.
        body = " ".join("".join(span.itertext()).split())
        if not body:
            _drop_element_keeping_tail(span)
        elif "$" in body:
            _drop_element_keeping_tail(span, body)   # 짝이 어긋나므로 감싸지 않는다
        else:
            _drop_element_keeping_tail(span, f"${_to_katex_math(body)}$")


def _replace_tex_images_with_markers(el) -> None:
    """수식 이미지 <img class="tex-formula"> 를 ⟦img:URL⟧ 마커 텍스트로 치환한다.

    구형 문제의 수식은 alt 없는 PNG 라 itertext() 평탄화에서 통째로 사라진다.
    프론트가 이 마커를 <img> 로 되살린다.
    """
    for img in el.xpath('.//img[contains(@class,"tex-formula")]'):
        src = img.get("src", "")
        if src:
            # 소비처 정규식이 https?:// 만 매칭한다 — 프로토콜 상대 경로를 절대 URL 로 승격한다.
            if not re.match(r'^https?://', src):
                src = urljoin("https://codeforces.com", src)
            _drop_element_keeping_tail(img, f"⟦img:{src}⟧")


def cf_xpath_text(tree, expr: str) -> str:
    """선택한 요소의 텍스트를 뽑는다.

    조회 전용이 아니라 tree 를 in-place 로 변경한다 — 선택된 서브트리에서
    script/style/section-title 과 수식 <img> 를 실제로 제거한다. 같은 tree 를 다른
    xpath 로 다시 읽으면 이미 제거된 상태를 본다.
    """
    nodes = tree.xpath(expr)
    if not nodes:
        return ""
    el = nodes[0]
    # script/noscript/style 은 MathJax 마크업이라 itertext() 에서 수식이 중복된다.
    # section-title 은 "Input"/"Output" 제목이 본문에 섞이는 것을 막으려고 제거한다.
    for unwanted in el.xpath(
        './/*[self::script or self::noscript or self::style'
        ' or contains(@class,"section-title")]'
    ):
        _drop_element_keeping_tail(unwanted)
    _replace_tex_spans_with_latex(el)
    _replace_tex_images_with_markers(el)
    return normalize_cf_math(" ".join(el.itertext()).strip())


def _extract_samples(container) -> list[dict]:
    """예제 입출력 쌍 목록.

    CF는 sample-test 가 문제당 하나이고 그 안에 input/output <pre> 쌍이 여러 개 들어간다.
    zip 대신 zip_longest 를 쓴다. 인터랙티브 문제처럼 output 이 없는 쪽이 섞이면
    zip 은 짧은 쪽에서 잘라 예제를 날린다. 없는 쪽은 빈 문자열로 보존한다.
    """
    samples = []
    for test in container.xpath('.//div[contains(@class,"sample-test")]'):
        inp_pres = test.xpath('.//div[contains(@class,"input")]//pre')
        out_pres = test.xpath('.//div[contains(@class,"output")]//pre')
        for inp, out in zip_longest(inp_pres, out_pres):
            samples.append({
                "input":  "\n".join(inp.itertext()).strip() if inp is not None else "",
                "output": "\n".join(out.itertext()).strip() if out is not None else "",
            })
    return samples


def _extract_cf_sections(tree) -> dict:
    return {
        "description": cf_xpath_text(tree, f'{_CF_PROBLEM_BASE_XPATH}/div[2]'),
        "input":       cf_xpath_text(tree, f'{_CF_PROBLEM_BASE_XPATH}/div[3]'),
        "output":      cf_xpath_text(tree, f'{_CF_PROBLEM_BASE_XPATH}/div[4]'),
    }


def get_cf_problem_sections(problem_ref: str) -> dict | None:
    """실패 시 None — 호출부가 빈 섹션으로 착각해 기존 README 본문을 지우지 않도록 구분한다."""
    try:
        from lxml import etree

        contest_id, index = normalize_codeforces_problem_ref(problem_ref)
        url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
        resp = requests.get(url, headers=CODEFORCES_HEADERS, timeout=15)
        resp.raise_for_status()

        tree = etree.fromstring(resp.content, etree.HTMLParser())
        return _extract_cf_sections(tree)
    except Exception as e:
        logger.warning("CF 문제 섹션 수집 실패 (%s): %s", problem_ref, e)
        return None


def scrape_cf_problem(problem_ref: str) -> dict:
    """CF 문제 페이지에서 제목/제한/본문/예제/노트를 raw(미번역)로 추출. 형식 오류 시 ValueError."""
    from lxml import etree

    contest_id, index = normalize_codeforces_problem_ref(problem_ref)

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    resp = requests.get(url, timeout=15, headers=CODEFORCES_HEADERS)
    resp.raise_for_status()

    tree = etree.fromstring(resp.content, etree.HTMLParser())

    def _limit_value(xpath_expr: str) -> str:
        nodes = tree.xpath(xpath_expr)
        if not nodes:
            return ""
        el = nodes[0]
        prop_nodes = el.xpath('.//*[contains(@class,"property-title")]')
        prop_text = " ".join(prop_nodes[0].itertext()).strip() if prop_nodes else ""
        full_text = " ".join(el.itertext()).strip()
        return full_text.replace(prop_text, "", 1).strip()

    note_text = cf_xpath_text(tree, '//*[contains(@class,"note")]')

    sample_container = tree.xpath(f'{_CF_PROBLEM_BASE_XPATH}/div[5]')
    samples = _extract_samples(sample_container[0]) if sample_container else []

    sections = _extract_cf_sections(tree)

    return {
        "title": cf_xpath_text(tree, '//div[@class="title"]') or f"CF {problem_ref}",
        "time_limit": _limit_value('//div[contains(@class,"time-limit")]'),
        "memory_limit": _limit_value('//div[contains(@class,"memory-limit")]'),
        "statement": sections["description"],
        "input": sections["input"],
        "output": sections["output"],
        "note": note_text,
        "samples": samples,
        "url": url,
        "contest_id": str(contest_id),
        "index": index,
    }


def _codeforces_api_request(method_name: str, params: dict | None = None,
                            api_key: str | None = None, api_secret: str | None = None) -> dict:
    params = {k: v for k, v in (params or {}).items() if v is not None}
    params["lang"] = "en"

    if api_key and api_secret:
        now = int(time.time())
        rand = f"{random.randint(0, 999999):06d}"
        signed_params = {**params, "apiKey": api_key, "time": now}
        sorted_items = sorted((str(k), str(v)) for k, v in signed_params.items())
        query = urlencode(sorted_items)
        sig_base = f"{rand}/{method_name}?{query}#{api_secret}"
        api_sig = rand + hashlib.sha512(sig_base.encode("utf-8")).hexdigest()
        signed_params["apiSig"] = api_sig
        params = signed_params

    # 쿼리스트링에 apiKey·apiSig 가 들어 있고 requests 예외 메시지는 요청 URL 전문을
    # 포함한다 — 이 함수를 나가는 예외는 전부 원문 없는 ValueError 로 치환한다.
    try:
        resp = requests.get(
            f"{CODEFORCES_API_BASE}/{method_name}",
            params=params,
            headers=CODEFORCES_HEADERS,
            timeout=30,
        )
    except requests.RequestException as e:
        # UpstreamUnavailable 이다 — 상류 장애를 400(입력 오류)으로 보고하면 안 된다.
        raise UpstreamUnavailable(f"Codeforces API 연결 실패 ({type(e).__name__})") from None
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if not isinstance(payload, dict):
        # 점검 페이지·프록시가 배열이나 문자열을 줄 수 있다 — dict 가 아니면 없는 것으로 본다.
        payload = None
    status = resp.status_code
    comment = payload.get("comment") if payload else None
    if status >= 500 or status in (403, 429):
        # 상태코드를 comment 보다 먼저 본다 — CF 는 레이트리밋·점검 응답에도 comment 를 실어 준다.
        raise UpstreamUnavailable(f"Codeforces API 오류 (HTTP {status})")
    if 400 <= status < 500 and comment:
        # CF 가 준 메시지를 그대로 쓴다 — 요청 URL 을 담지 않아 서명이 새지 않는다.
        raise ValueError(comment)
    if status >= 400:
        raise ValueError(f"Codeforces API 오류 (HTTP {status})")
    if payload is None or payload.get("status") != "OK":
        # 2xx 인데 JSON 이 아니거나 status 가 OK 가 아닌 응답이다.
        raise UpstreamUnavailable("Codeforces API 응답을 해석할 수 없습니다.")
    result = payload.get("result")
    if result is None:
        # status 는 OK 인데 result 가 없다 — CF 가 자기 계약을 깬 경우다.
        raise UpstreamUnavailable("Codeforces API 응답에 result 가 없습니다.")
    return result


def _fetch_cf_problemset() -> tuple[list[dict], dict]:
    """problemset.problems 전체 다운로드 — (문제 목록, solvedCount 맵).
    빈 응답은 raise 한다. 호출부가 성공했을 때만 스냅샷을 교체하므로 실패가 박제되지 않는다."""
    result = _codeforces_api_request("problemset.problems")
    problems = result.get("problems", [])
    if not problems:
        raise ValueError("Codeforces problemset 응답이 비어 있습니다.")
    stats_map = {}
    for s in result.get("problemStatistics", []):
        contest_id = s.get("contestId")
        index = s.get("index")
        if not contest_id or not index:
            continue
        stats_map[(contest_id, index)] = s.get("solvedCount", 0)
    return problems, stats_map


def _build_lookup(problems: list[dict]) -> dict[tuple[int, str], dict]:
    lookup = {}
    for problem in problems:
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if contest_id and index:
            lookup[(contest_id, index)] = problem
    return lookup


def _install_snapshot(fresh: tuple[list[dict], dict]) -> None:
    """락을 잡은 상태에서만 부른다.

    **`_snapshot` 대입이 "준비 완료" 신호이므로 반드시 마지막이어야 한다.**
    `_get_cf_problemset_snapshot` 의 빠른 경로는 락을 잡지 않으므로, `_snapshot` 을 먼저
    공개하면 그 사이 들어온 스레드가 아직 None 인 `_lookup` 을 받아
    `AttributeError: 'NoneType' object has no attribute 'get'` 로 죽는다.
    창이 열리는 시점이 하필 "프로세스당 한 번, 수 초짜리 다운로드 직후" 라
    콜드 스타트에 요청이 몰리는 정확히 그 순간이다.
    """
    global _snapshot, _lookup
    _lookup = _build_lookup(fresh[0])
    _snapshot = fresh


def _get_cf_problemset_snapshot() -> tuple[list[dict], dict]:
    """프로세스당 1회 받아 재사용한다. 성공 후에는 락 없는 빠른 경로다."""
    if _snapshot is not None:
        return _snapshot
    with _snapshot_lock:
        # 이중 확인 — 기다리는 동안 다른 스레드가 이미 채웠으면 그대로 쓴다.
        if _snapshot is None:
            _install_snapshot(_fetch_cf_problemset())
    return _snapshot


def _get_codeforces_problem_lookup() -> dict[tuple[int, str], dict]:
    _get_cf_problemset_snapshot()
    return _lookup


def _try_refresh_snapshot() -> bool:
    """쿨다운을 소비하고 스냅샷을 새로 받는다. **성공했을 때만** 교체한다.

    스냅샷은 프로세스 기동 시점에 고정되므로 그 뒤 새로 열린 대회의 문제는 miss 가 난다.
    주기적 TTL 대신 실제 miss 에서만 갱신하되, 쿨다운 중이면 곧바로 miss 로 둔다
    (오타 반복이 매번 전체 재다운로드로 번지지 않도록).
    """
    global _last_force_refresh
    now = time.time()
    # 락 밖에서 먼저 본다 — 갱신 중인 스레드를 기다려도 어차피 쿨다운에 걸린다.
    if now - _last_force_refresh < _FORCE_REFRESH_COOLDOWN:
        return False
    if not _snapshot_lock.acquire(blocking=False):
        return False   # 이미 다른 스레드가 갱신 중이다
    try:
        if now - _last_force_refresh < _FORCE_REFRESH_COOLDOWN:
            return False
        _last_force_refresh = now
        try:
            fresh = _fetch_cf_problemset()
        except Exception as e:
            # 기존 스냅샷을 그대로 둔다 — 여기서 비우면 CF 기능 전부가 열화된다.
            logger.warning("CF 스냅샷 갱신 실패 — 기존 스냅샷을 유지한다: %s", e)
            return False
        _install_snapshot(fresh)
        return True
    finally:
        _snapshot_lock.release()


def get_codeforces_user_info(handle: str) -> dict:
    users = _codeforces_api_request("user.info", {"handles": handle})
    if not users:
        raise ValueError("Codeforces 유저를 찾을 수 없습니다.")
    return users[0]


def get_codeforces_user_submissions(handle: str, count: int = 1000,
                                    api_key: str | None = None,
                                    api_secret: str | None = None) -> list[dict]:
    from clients.utils import get_problem_url
    result = _codeforces_api_request(
        "user.status",
        {"handle": handle, "from": 1, "count": count, "includeSources": "true" if api_key and api_secret else None},
        api_key=api_key,
        api_secret=api_secret,
    )
    submissions = []
    seen = set()
    for sub in result:
        if sub.get("verdict") != "OK":
            continue
        problem = sub.get("problem") or {}
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if not contest_id or not index:
            continue
        problem_ref = f"{contest_id}{index}"
        if problem_ref in seen:
            continue
        seen.add(problem_ref)
        submissions.append({
            "problem_ref": problem_ref,
            "title": problem.get("name", problem_ref),
            "tier_name": cf_rating_label(problem.get("rating")),
            "tags": problem.get("tags", []),
            "language": sub.get("programmingLanguage", ""),
            "code": sub.get("source", "") or "",
            "problem_url": get_problem_url("codeforces", problem_ref),
        })
    return submissions


def search_cf_problems_by_tag(tag: str, min_rating: int, max_rating: int,
                               exclude_refs: set) -> list[dict]:
    # 태그별 API 재호출 대신 프로세스 1회 스냅샷을 로컬 필터링 — 테마/추천에서 반복 호출돼도 fetch는 1번.
    try:
        problems, stats_map = _get_cf_problemset_snapshot()
    except Exception as e:
        # 전면 실패를 빈 목록으로 돌려주면 호출부가 "다 풀었음"과 구분할 수 없다.
        logger.warning("CF 문제셋 스냅샷 조회 실패: %s", e)
        raise ProblemSearchError("Codeforces 문제 검색에 실패했습니다.") from e

    results = []
    for p in problems:
        if tag not in p.get("tags", []):
            continue
        rating = p.get("rating", 0)
        if not rating or not (min_rating <= rating <= max_rating):
            continue
        contest_id = p.get("contestId")
        index = p.get("index", "")
        if not contest_id or not index:
            continue
        ref = f"{contest_id}{index}"
        if ref in exclude_refs:
            continue
        results.append({
            "id": ref,
            "title": p.get("name", ref),
            "tier": 0,
            # 배지 표시 전용 짧은 라벨. 저장 경로로 흘리면 안 된다 —
            # 리뷰에 남는 라벨은 cf_rating_label('Codeforces N')이고 평균 레이팅 파서가 그 접두사를 읽는다.
            "tier_name": f"CF {rating}",
            "rating": rating,
            "url": f"https://codeforces.com/problemset/problem/{contest_id}/{index}",
            "_solved_count": stats_map.get((contest_id, index), 0),
        })

    results.sort(key=lambda x: -x["_solved_count"])
    for r in results:
        del r["_solved_count"]
    return results
