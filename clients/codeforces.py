import re
import time
import random
import hashlib
from functools import lru_cache
from itertools import zip_longest
from urllib.parse import urlencode, urljoin
import requests
from bs4 import BeautifulSoup

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


def get_codeforces_problem_info(problem_ref: str) -> dict:
    from clients.utils import get_problem_url
    contest_id, index = normalize_codeforces_problem_ref(problem_ref)
    problem = _get_codeforces_problem_lookup().get((contest_id, index))
    if not problem:
        # 스냅샷은 프로세스 기동 시점에 한 번 고정된다 — 그 뒤 새로 열린 대회의 문제는
        # miss가 난다. 주기적 TTL 대신 실제 miss가 났을 때만 1회 강제 갱신 후 재조회한다.
        _get_cf_problemset_snapshot.cache_clear()
        _get_codeforces_problem_lookup.cache_clear()
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
        except Exception:
            continue

    return "문제 설명 자동 수집에 실패했습니다. 제목, 난이도, 태그 기준으로 제한적으로 분석합니다."


def normalize_cf_math(text: str) -> str:
    """CF 의 수식 구분자($$$…$$$ / $$$$$$…$$$$$$)를 프론트(KaTeX)가 쓰는 $…$ / $$…$$ 로 바꾼다.

    번역 실패 시 원문이 그대로 프론트로 나가므로 번역 단계가 아니라 스크래핑 단계에서 통일한다.
    디스플레이(6달러)를 먼저 처리해야 인라인 규칙이 앞의 3달러만 먹고 짝을 어긋내지 않는다.
    """
    text = re.sub(r'\$\$\$\$\$\$(.+?)\$\$\$\$\$\$', r'$$\1$$', text, flags=re.DOTALL)
    return re.sub(r'\$\$\$(.+?)\$\$\$', r'$\1$', text, flags=re.DOTALL)


# 수식 이미지 마커의 유일한 정의. 소비처가 셋이라 포맷이 어긋나면 조용히 깨진다 —
# 번역 마스킹(cf_translator), README 변환(tex_markers_to_markdown),
# 모달 렌더링(static/js/problem-modal.js 의 restoreFormulaImages).
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


# KaTeX 0.16 이 유니코드 그대로 인식하지 못하는 기호만 LaTeX 명령으로 바꾼다.
# ≤ ≥ ≈ ∑ √ ⌊ 등은 그대로 렌더되므로 건드리지 않는다(katex.min.js 심볼 테이블 실측).
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
            # 소비처(cf_translator/tex_markers_to_markdown/problem-modal.js) 정규식이
            # https?:// 만 매칭한다 — "//espresso.codeforces.com/..." 같은 프로토콜 상대
            # 경로는 절대 URL로 승격해야 README에 리터럴 마커가 그대로 남지 않는다.
            if not re.match(r'^https?://', src):
                src = urljoin("https://codeforces.com", src)
            _drop_element_keeping_tail(img, f"⟦img:{src}⟧")


def cf_xpath_text(tree, expr: str) -> str:
    """선택한 요소의 텍스트를 뽑는다.

    주의: 조회 전용이 아니라 tree 를 in-place 로 변경한다 — 선택된 서브트리에서
    script/style/section-title 과 수식 <img> 를 실제로 제거한다. 같은 tree 를 다른
    xpath 로 다시 읽는 코드를 추가할 때는 이미 제거된 상태를 본다는 점에 유의할 것.
    """
    nodes = tree.xpath(expr)
    if not nodes:
        return ""
    el = nodes[0]
    # script/noscript/style 텍스트는 MathJax 마크업이라 itertext()에 포함되면 수식 중복 발생.
    # section-title은 "Input"/"Output" 같은 섹션 제목이 본문 텍스트에 섞여 중복되는 것을 막기 위해 제거.
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

    CF는 sample-test 가 문제당 하나이고 그 안에 input/output <pre> 쌍이 여러 개 들어간다 —
    컨테이너 단위로 순회하며 첫 쌍만 취하면 2번째 이후 예제가 통째로 사라진다.
    zip 대신 zip_longest 를 쓰는 이유: 인터랙티브 문제처럼 output 이 없는 쪽이 섞이면
    zip 은 짧은 쪽에서 잘라 예제 전체를 날린다. 없는 쪽은 빈 문자열로 보존한다.
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
    except Exception:
        return None


def scrape_cf_problem(problem_ref: str) -> dict:
    """CF 문제 페이지에서 제목/제한/본문/예제/노트를 raw(미번역)로 추출. 형식 오류 시 ValueError."""
    from lxml import etree

    contest_id, index = normalize_codeforces_problem_ref(problem_ref)

    url = f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    resp = requests.get(url, timeout=10, headers={
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    })
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

    resp = requests.get(
        f"{CODEFORCES_API_BASE}/{method_name}",
        params=params,
        headers=CODEFORCES_HEADERS,
        timeout=30,
    )
    # CF API 는 실패 시 HTTP 400 + {"status":"FAILED","comment":"..."} 를 준다. comment 를
    # raise_for_status() 보다 먼저 확인해야 한다 — 그러지 않으면 이 흔한 실패에서 CF 의 친절한
    # 메시지 대신 requests 의 HTTPError 전문(요청 URL의 apiKey/apiSig 포함)이 그대로 새어나간다.
    try:
        payload = resp.json()
    except ValueError:
        payload = None
    if payload and payload.get("comment"):
        raise ValueError(payload["comment"])
    resp.raise_for_status()
    if payload is None or payload.get("status") != "OK":
        raise ValueError("Codeforces API 오류")
    return payload["result"]


@lru_cache(maxsize=1)
def _get_cf_problemset_snapshot() -> tuple[list[dict], dict]:
    """problemset.problems 전체를 프로세스당 1회만 받아온다 — (문제 목록, solvedCount 맵).
    빈 응답은 raise 해서 실패가 lru_cache에 박제되지 않게 한다."""
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


@lru_cache(maxsize=1)
def _get_codeforces_problem_lookup() -> dict[tuple[int, str], dict]:
    lookup = {}
    problems, _ = _get_cf_problemset_snapshot()
    for problem in problems:
        contest_id = problem.get("contestId")
        index = str(problem.get("index", "")).upper()
        if contest_id and index:
            lookup[(contest_id, index)] = problem
    return lookup


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
    except Exception:
        return []

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
