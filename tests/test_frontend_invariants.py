"""프론트엔드 불변식.

빌드 스텝이 없어 JS 배선 끊김을 잡는 자동 방어선이 문자열 수준 검사뿐이다. 정확 문자열 대신
**정규식**으로 쓴다 — 공백·인용부호·줄바꿈이 바뀌면 거짓 빨강이 나고, 그 때문에 검사를
느슨하게 만들면 거짓 초록이 된다.

여기 고정하는 것은 전부 "고쳐 놓으면 조용히 되돌아가는" 성질의 결함이다.
"""
import re
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parent.parent / "static" / "js"
# 전 파일을 읽는다. 목록을 고정하면 "전 파일에서 원시 fetch 를 막는다" 같은 검사가
# 그 목록만 순회해, 밖의 파일에는 무엇을 넣어도 통과한다.
_MIN_JS_FILES = 20


def _js_function_body(src, signature):
    """`signature` 로 시작하는 함수의 본문을 중괄호 균형으로 잘라낸다.

    문자 수 윈도우로 찾으면 함수에 한두 줄만 추가돼도 "호출이 사라졌다"는 틀린 메시지로
    빨강이 난다. 이 파일 docstring 이 경계하는 패턴이다.
    """
    start = src.index(signature)
    # 매개변수 목록 안의 중괄호(구조 분해 기본값 `({ force = false } = {})`)를 본문으로
    # 착각하면 안 된다 — 괄호 깊이 0 에서 처음 만나는 `{` 가 본문이다.
    depth = 0
    brace = None
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
        elif src[i] == "{" and depth == 0:
            brace = i
            break
    assert brace is not None, f"{signature} 의 본문 시작을 찾지 못했다"
    depth = 0
    for i in range(brace, len(src)):
        if src[i] == "{":
            depth += 1
        elif src[i] == "}":
            depth -= 1
            if depth == 0:
                return src[brace:i + 1]
    raise AssertionError(f"{signature} 의 닫는 괄호를 찾지 못했다")


@pytest.fixture(scope="module")
def js():
    """static/js 파일 본문을 이름으로 읽는다.

    HTTP 가 아니라 디스크에서 읽는다 — 여기서 고정하는 것은 서빙 여부가 아니라 내용이고,
    자산이 실제로 서빙되는지는 test_index_assets·test_load_submission_wiring 이 본다.
    """
    out = {p.name: p.read_text(encoding="utf-8") for p in sorted(_JS_DIR.glob("*.js"))}
    # 개수 하한을 함께 둔다 — 경로가 틀리면 빈 dict 로 모든 루프 검사가 조용히 통과한다.
    assert len(out) >= _MIN_JS_FILES, f"JS 파일이 {len(out)}개뿐이다 — 경로를 확인하라"
    return out


def test_run_samples_restores_the_button_in_a_finally_block(js):
    """예제 실행 루프가 어떻게 끝나든 버튼을 되돌려야 한다.

    결과 노드가 사라진 뒤 catch 안에서 그 노드를 다시 참조하면 예외가 함수를 탈출해
    버튼이 disabled + '실행 중...' 으로 고착된다(새로고침 외 복구 불가).
    """
    src = js["problem-modal.js"]
    assert re.search(r"function\s+resetRunButton\s*\(", src)

    # finally 로 복원한다 — 다만 **내 세대일 때만**. 무조건 되돌리면 무효화된 옛 실행의
    # 늦은 응답이 새로 진행 중인 실행의 버튼을 활성으로 만들고, 그 상태에서 다시 누르면
    # 진행 중인 결과가 지워진다.
    run_samples = _js_function_body(src, "async function runSamples")
    assert "finally" in run_samples, "runSamples 에 finally 가 없다"
    finally_block = run_samples.split("finally", 1)[1]
    assert "resetRunButton()" in finally_block
    assert re.search(r"runToken\s*===\s*_runToken", finally_block), \
        "세대 확인 없이 되돌리면 진행 중인 실행의 버튼을 되살린다"

    # 모달을 열 때·닫을 때도 진행 중인 실행을 무효화하고 버튼을 되돌린다.
    # 문자 수 윈도우로 찾으면 함수에 한두 줄만 추가돼도 거짓 빨강이 난다 —
    # 함수 본문을 잘라내고 그 안에서 찾는다.
    for fn in ("function closeProblemModal", "async function openProblemModal"):
        body = _js_function_body(src, fn)
        assert "resetRunButton()" in body, f"{fn} 이 버튼을 복원하지 않는다"
        assert "_runToken++" in body, f"{fn} 이 진행 중인 실행을 무효화하지 않는다"


def test_run_samples_guards_the_result_node_before_writing(js):
    """사라진 노드에 쓰면 안 된다 — 노드 확인 없이 outerHTML 에 대입하면 TypeError 다."""
    src = js["problem-modal.js"]
    assert not re.search(r"document\.getElementById\(tcId\)\.outerHTML", src), \
        "노드 존재 확인 없이 outerHTML 에 대입하면 안 된다"
    assert re.search(r"const\s+cell\s*=\s*document\.getElementById\(tcId\)[\s\S]{0,120}?if\s*\(cell\)", src)


def test_all_fill_review_form_entry_points_confirm_overwrite():
    """진입점 넷이 같은 규약을 따라야 한다.

    한 곳만 검사하면 나머지에서 확인 호출을 지워도 통과한다 — 편집 중인 코드를 경고 없이
    덮어쓰게 된다. 네 진입점을 모두 순회한다.
    """
    entry_points = {
        "problem-modal.js": "proceedToReview",
        "load-submission.js": "지난 제출 불러오기 버튼",
        "history.js": "리뷰 기록 모달",
        "command-palette.js": "⌘K 팔레트",
    }
    for name, label in entry_points.items():
        src = (_JS_DIR / name).read_text(encoding="utf-8")
        assert "fillReviewForm(" in src, f"{name}({label}) 이 로더를 쓰지 않는다"
        # 두 문자열이 파일 어딘가에 각각 1회 있는 것으로는 부족하다 — 확인이 **호출보다
        # 앞에** 있는지 본다.
        guard = re.search(r"if\s*\(!confirmEditorOverwrite\(\)\)\s*return", src)
        assert guard, f"{name}({label}) 이 덮어쓰기 확인을 건너뛴다"
        # 정의(`function fillReviewForm(`)는 호출이 아니다 — load-submission.js 는
        # 로더를 정의하면서 자기 버튼에서 호출도 한다.
        call = re.search(r"(?<!function )\bfillReviewForm\(", src)
        assert call, f"{name}({label}) 에 fillReviewForm 호출이 없다"
        assert guard.start() < call.start(), (
            f"{name}({label}) 에서 덮어쓰기 확인이 fillReviewForm 호출보다 뒤에 있다")


def test_imported_review_refetches_instead_of_mutating_a_snapshot(js):
    """AI 리뷰가 끝나면 목록을 **서버에서 다시 받는다**.

    서버가 그 행을 실제로 지우므로 화면도 그것을 반영해야 한다. 클라이언트가 들고 있는
    스냅샷을 고쳐서 맞추면, 그 스냅샷을 잡은 늦은 호출이 나중에 화면을 되돌린다(리뷰 완료
    직후 목록이 옛 개수로 후퇴). 목록의 정본을 서버 하나로 두면 그 경로가 사라진다.
    """
    src = js["import-history.js"]
    body = _js_function_body(src, "async function requestImportedReview")
    assert body.count("refreshImportList()") >= 2, \
        "성공·실패 양쪽에서 목록을 다시 받아야 한다"
    assert "splice(" not in src, "목록 스냅샷을 직접 고치면 안 된다 — 서버가 정본이다"
    assert "allProblems" not in src, "목록 전체를 클로저에 잡지 않는다"


def test_tier_chart_consumes_the_server_order_without_re_deriving_it(js):
    """문제당 첫 등장만 남기는 규칙은 서버(db.get_tier_history) 한 곳에만 둔다.

    같은 규칙을 프론트에도 두면 한쪽만 바뀌어 갈린다. 마지막 회차를 남기는 쪽으로 갈리면
    재제출이 과거 곡선을 소급 변경한다 — tier 는 회차가 아니라 문제의 속성이라 값은 같고
    그 문제가 시계열에 놓이는 날짜만 이동하기 때문이다.
    (동작 자체는 test_db_untested_queries.py 가 실제 데이터로 고정한다.)
    """
    src = js["tier-chart.js"]
    assert ".reverse()" not in src, "reverse 하면 문제당 마지막 회차가 남는다"
    # 날짜 키 정렬(Object.keys(byDate).sort())은 정당하다 — 금지 대상은 회차 행의 재정렬이다.
    assert not re.search(r"history\.sort\(", src), "서버가 오름차순으로 준다 — 재정렬은 순서를 뒤집는다"
    assert not re.search(r"seenPids|new Set\(", src), "중복 제거를 프론트에 다시 두지 않는다"
    assert re.search(r"history\.forEach\(", src), "서버가 준 순서 그대로 1패스여야 한다"


def test_pasted_statement_wins_over_the_viewer_cache(js):
    """서버 resolve_statement 와 같은 우선순위여야 LLM 리뷰와 README 가 갈리지 않는다."""
    assert re.search(r"description:\s*pastedStatement\s*\|\|\s*cfSections", js["review.js"])


def test_markdown_rendering_falls_back_when_the_cdn_is_blocked(js):
    """CDN 이 막히면 서버가 이미 저장·과금한 리뷰 결과가 화면에서 사라진다."""
    assert re.search(r"function\s+renderMarkdown\s*\(", js["utils.js"])
    assert re.search(r"typeof\s+marked\s*===\s*['\"]undefined['\"]", js["utils.js"])
    # 렌더 지점은 전부 헬퍼를 거쳐야 한다 — 직접 호출이 남아 있으면 그 경로만 가드가 없다.
    # 목록을 고정하면 그 밖의 파일이 직접 불러도 통과한다.
    for name, src in js.items():
        if name == "utils.js":
            continue          # 헬퍼 정의 자체가 여기 있다
        assert "marked.parse" not in src, f"{name} 이 marked 를 직접 부른다"
        assert "DOMPurify.sanitize" not in src, f"{name} 이 DOMPurify 를 직접 부른다"


def test_outage_is_not_reported_as_empty_data(js):
    """res.ok 를 안 보면 503(온디맨드 DB 정지)이 '기록이 없습니다'로 표시된다."""
    # 전 파일에서 원시 fetch 를 막고, utils.js 안의 fetchJsonOk 정의 한 곳만 예외로 둔다.
    for name, src in js.items():
        for line_no, line in enumerate(src.split("\n"), 1):
            # 전역 별칭도 원시 호출이다(`window.` `globalThis.` `self.`). 룩비하인드로
            # `.` 만 걸러내면 그 형태들이 통과하므로, 앞에 오는 전역 이름을 함께 본다.
            if not re.search(
                    r"(?<![.\w])fetch\s*\(|\b(?:window|globalThis|self)\s*\.\s*fetch\s*\(",
                    line):
                continue
            assert name == "utils.js", (
                f"{name}:{line_no} 이 원시 fetch 를 쓴다 — fetchJsonOk 를 써야 한다")
    assert re.search(r"async function fetchJsonOk", js["utils.js"])
    for name in ("tier-chart.js", "import-history.js", "history.js"):
        assert "fetchJsonOk(" in js[name], f"{name} 이 fetchJsonOk 를 쓰지 않는다"


def test_code_view_caches_only_successful_loads(js):
    """404 에도 loaded 를 세우면 오류 상태가 영구 캐시돼 재시도가 막힌다."""
    src = js["import-history.js"]
    body = _js_function_body(src, "async function toggleCodeView")
    # 양성 단정을 함께 둔다 — 부정 단정만 있으면 대입을 통째로 지워도 통과한다.
    assert re.search(r"dataset\.loaded\s*=", body), "성공 경로에 loaded 표시가 없다"
    # catch 블록 안에는 없어야 한다(문자 수 윈도우 대신 중괄호 균형으로 자른다).
    catch_body = _js_function_body(body[body.index("} catch"):], "catch")
    assert "dataset.loaded" not in catch_body


def test_loading_labels_are_specific_per_button(js):
    """기본 문구가 '분석 중...' 이면 기록 불러오기·추천받기에도 그게 뜬다."""
    assert re.search(r"loadingLabel\s*\|\|\s*['\"]처리 중", js["utils.js"])
    for name in ("history.js", "stats.js"):
        assert "dataset.loadingLabel" in js[name], f"{name} 버튼에 로딩 문구가 없다"


def test_tabify_indent_only_transforms_aligned_indentation(js):
    """폭이 INDENT_WIDTH 의 배수가 아닌 들여쓰기를 변환하면 탭/스페이스가 섞여 파이썬이
    TabError 로 거부한다(실측: 2·3칸 들여쓰기 붙여넣기). 배수가 아니면 원문을 그대로 둔다."""
    body = _js_function_body(js["editor.js"], "function tabifyIndent")
    assert re.search(r"%\s*INDENT_WIDTH\s*===\s*0", body), \
        "들여쓰기 폭이 INDENT_WIDTH 의 배수인지 검사하는 가드가 없다"
    assert re.search(r"return code;", body), \
        "배수가 아니면 원문을 그대로 반환해야 한다"


def test_repo_select_listener_is_bound_once(js):
    """데이터 로딩 함수 안에서 리스너를 걸면 재호출 시 누적된다."""
    assert re.search(r"repoSelect\.dataset\.bound", js["github.js"])
    # 바인딩이 있는 형태(`} catch (e) {}`)도 빈 catch 다 — 괄호를 선택으로 둔다.
    assert not re.search(r"\}\s*catch\s*(?:\([^)]*\)\s*)?\{\s*\}", js["github.js"]), (
        "빈 catch 는 실패를 무음으로 만든다")


# ── 접근성·CSS 불변식 ──

_CSS_DIR = Path(__file__).resolve().parent.parent / "static" / "css"
_HTML = Path(__file__).resolve().parent.parent / "static" / "index.html"


def _strip_css_comments(src):
    """규칙을 찾는 검사는 주석을 봐서는 안 된다 — 결함을 설명하는 주석에 그 결함의
    코드 형태가 그대로 적혀 있어 거짓 빨강이 난다."""
    return re.sub(r"/\*.*?\*/", "", src, flags=re.S)


@pytest.fixture(scope="module")
def css():
    """주석을 제거한 본문. 주석 자체를 봐야 하는 검사는 raw_css 를 쓴다."""
    return {p.name: _strip_css_comments(p.read_text(encoding="utf-8"))
            for p in _CSS_DIR.glob("*.css")}


@pytest.fixture(scope="module")
def raw_css():
    return {p.name: p.read_text(encoding="utf-8") for p in _CSS_DIR.glob("*.css")}


@pytest.fixture(scope="module")
def html():
    return _HTML.read_text(encoding="utf-8")


def test_control_borders_use_the_dedicated_token(css):
    """폼·버튼·칩의 경계선은 WCAG 1.4.11(비텍스트 3:1) 대상이다.

    --line/--line-strong 은 1.15~1.68:1 이라 이 기준에 못 미친다. 배경이 지면과
    1.03~1.06:1 이라 테두리가 유일한 식별 수단인 컨트롤에만 전용 토큰을 쓴다.
    """
    tokens = css["tokens.css"]
    assert re.search(r"--line-control:\s*#646B73", tokens), "다크 값"
    assert re.search(r"--line-control:\s*#848B93", tokens), "라이트 값"

    comp = css["components.css"]
    # 폼 컨트롤 공통 블록
    form_block = comp.split('input[type="text"], input[type="password"], textarea, select')[1][:400]
    assert "var(--line-control)" in form_block


def test_chrome_does_not_consume_verdict_tokens(css):
    """크롬 요소가 --eff-* 를 직접 쓰면 효율 판정 팔레트를 조정할 때 함께 변한다.

    "GitHub 연결됨" 배지와 "효율적" 판정이 같은 토큰을 쓰면 한쪽을 조정할 때 다른 쪽이
    함께 변한다. --eff-* 는 판정 배지(.eff-*)와 리뷰 결과(.points-box)만 쓴다.
    """
    for name in ("components.css", "surfaces.css", "layout.css", "base.css"):
        for line_no, line in enumerate(css[name].split("\n"), 1):
            if "var(--eff-" not in line:
                continue
            allowed = line.lstrip().startswith(".eff-") or ".points-box" in line
            assert allowed, f"{name}:{line_no} 이 판정 토큰을 직접 쓴다 — {line.strip()[:70]}"


def test_javascript_does_not_consume_verdict_tokens(js):
    """CSS 만 훑으면 소비처의 절반을 못 본다 — 통계 바와 티어 차트 색은 JS 가 읽는다.

    통계 바와 티어 차트는 getComputedStyle 로 토큰을 읽으므로 위 CSS 전용 검사에 걸리지
    않는다. 데이터 시각화는 --bar-*/--chart-line 을 쓴다(tokens.css 에서 --eff-* 를
    별칭으로 두므로 색은 같다).
    """
    for name, src in js.items():
        for line_no, line in enumerate(src.split("\n"), 1):
            assert "--eff-" not in line, (
                f"{name}:{line_no} 이 판정 토큰을 직접 읽는다 — {line.strip()[:70]}")
    assert "--chart-line" in js["tier-chart.js"], "차트가 전용 토큰을 쓰지 않는다"
    assert "--bar-high" in js["stats.js"], "통계 바가 전용 토큰을 쓰지 않는다"


def test_cmdk_input_selector_beats_the_element_selector(css):
    """input[type="text"] 는 (0,1,1) 이라 .cmdk-input (0,1,0) 을 순서와 무관하게 이긴다.

    요소 선택자를 함께 붙이지 않으면 이 블록의 선언이 전부 무효가 된다.
    """
    assert re.search(r"input\.cmdk-input\s*\{", css["surfaces.css"])
    assert not re.search(r"^\.cmdk-input\s*\{", css["surfaces.css"], re.M)


def test_editor_focus_ring_is_on_the_wrapper(css):
    """래퍼에 overflow:hidden 이 있으므로 내부 요소의 outline 은 전량 클리핑된다."""
    src = css["surfaces.css"]
    assert re.search(r"\.cm-wrap:focus-within,\s*\.pm-code:focus-within\s*\{[^}]*outline:", src)
    # 내부 .CodeMirror 에는 outline 을 주지 않는다.
    inner = re.search(r"\.cm-wrap:focus-within \.CodeMirror[^{]*\{([^}]*)\}", src)
    assert inner and "outline" not in inner.group(1)


def test_row_hairlines_do_not_depend_on_dom_structure(css):
    """목록 행의 구분선이 컨테이너 구조에 의존하면 안 된다.

    쓰면 안 되는 셀렉터가 둘이다. ① `.row:first-child` — #history-list 의 첫 자식은 항상
    .toolbar 라 리뷰 기록 탭에서 매칭되지 않는다. ② `.row + .row` — 가져오기 목록은 행마다
    코드 보기 패널 div 를 형제로 끼워 넣고, 인접(+)은 DOM 구조 기준이라 display:none
    형제도 인접을 끊어 그 탭에서만 구분선이 2px 로 겹친다.

    일반 형제(~)는 중간 노드와 무관하게 매칭된다.
    """
    src = css["components.css"]
    assert not re.search(r"\.row:first-child", src), "구조 의존 셀렉터를 쓰고 있다"
    assert not re.search(r"\.row \+ \.row", src), "인접 결합자는 중간 노드에 깨진다"
    assert re.search(r"\.row ~ \.row\s*\{[^}]*border-top:\s*none", src)


def test_mono_weights_stay_within_the_loaded_faces(css, html):
    """웹폰트는 mono 400/500 만 로드한다 — 600 을 지정하면 합성 볼드가 된다."""
    loaded = set(re.findall(r"jetbrains-mono@[\d.]+/(\d+)\.css", html))
    assert loaded == {"400", "500"}, f"로드된 굵기: {loaded}"
    for name, src in css.items():
        for block in re.findall(r"\{[^{}]*\}", src):
            if "--font-mono" in block or "font-mono" in block:
                assert "font-weight: 600" not in block, f"{name}: {block.strip()[:70]}"


def test_tabs_have_a_keyboard_pattern(js, html):
    """role="tablist" 를 선언했으면 화살표 키 이동과 roving tabindex 가 있어야 한다."""
    src = js["tabs.js"]
    # 단순 부분문자열 검사는 오타(ArrowRightX)를 통과시킨다 — 실제 키 매핑을 본다.
    for key in ("ArrowRight", "ArrowLeft", "ArrowDown", "ArrowUp"):
        assert re.search(key + r"\s*:\s*-?1", src), f"{key} 매핑이 없다"
    assert re.search(r"e\.key\s*===\s*['\"]Home['\"]", src)
    assert re.search(r"e\.key\s*===\s*['\"]End['\"]", src)
    assert re.search(r"setAttribute\(['\"]tabindex['\"],\s*['\"]-1['\"]\)", src)
    # 마크업의 초기 상태도 맞아야 한다(JS 실행 전).
    tab_buttons = re.findall(r'<button[^>]*\brole="tab"[^>]*>', html)
    assert len(tab_buttons) == 7, f"탭 버튼 수: {len(tab_buttons)}"
    selected = [b for b in tab_buttons if 'aria-selected="true"' in b]
    assert len(selected) == 1 and 'tabindex="0"' in selected[0]
    assert 'aria-controls="tab-review"' in selected[0]
    # 나머지는 roving tabindex 규약상 전부 -1 이어야 한다(JS 실행 전 초기 상태).
    assert all('tabindex="-1"' in b for b in tab_buttons if b not in selected)


def _controls_without_names(markup: str) -> list[str]:
    """이름 없는 <input>/<select>/<textarea> 태그를 모은다.

    이름의 근거로 인정하는 것: aria-label · aria-labelledby · 같은 마크업 안의
    `for="<id>"`. placeholder 는 접근 가능한 이름이 **아니다**(WCAG 4.1.2).
    type=hidden 과 버튼류는 제외한다.
    """
    labelled_ids = set(re.findall(r'\bfor="([^"]+)"', markup))
    bad = []
    for tag in re.findall(r"<(?:input|select|textarea)\b[^>]*>", markup):
        if re.search(r'type="(?:hidden|submit|button|checkbox|radio)"', tag):
            continue
        if "aria-label" in tag:
            continue
        tag_id = re.search(r'\bid="([^"]+)"', tag)
        if tag_id and tag_id.group(1) in labelled_ids:
            continue
        bad.append(tag[:90])
    return bad


def test_every_form_control_has_an_accessible_name(html, js):
    """<summary> 는 label 이 아니고 placeholder 도 접근 가능한 이름이 아니다.

    마크업 한 곳만 검사하면 JS 가 만드는 컨트롤이 이름 없이 남아 있어도 통과한다 —
    HTML 과 JS 를 모두 훑는다.
    """
    block = html.split('id="problem-statement"')[1][:200]
    assert 'aria-label="문제 설명"' in block

    bad = _controls_without_names(html)
    for name, src in js.items():
        bad += [f"{name}: {tag}" for tag in _controls_without_names(src)]
    assert not bad, "접근 가능한 이름이 없는 폼 컨트롤:\n  " + "\n  ".join(bad)


def test_hints_are_linked_to_their_controls(html):
    """id 는 있는데 아무도 참조하지 않으면 스크린리더가 읽지 않는다."""
    for control, hint in (("problem-id", "problem-id-help"),
                          ("code-language", "code-language-help")):
        block = html.split(f'id="{control}"')[1][:200]
        assert f'aria-describedby="{hint}"' in block, control


def test_toggles_expose_pressed_state(html):
    """개수 하한(>= 4)만 세면 하나를 지워도 통과한다 — 토글 그룹마다 짝을 확인한다."""
    for attr in ("data-platform", "data-themes-platform", "data-report-platform"):
        buttons = re.findall(rf"<button[^>]*\b{attr}=[^>]*>", html)
        assert len(buttons) >= 2, f"{attr} 토글이 2개 미만이다"
        for b in buttons:
            assert "aria-pressed" in b, f"aria-pressed 가 없다: {b[:80]}"


def test_modals_live_outside_the_tab_sections(html):
    """탭 섹션 안에 있으면 다른 탭 활성 시 조상이 display:none 이 되어 열 수 없다."""
    main_end = html.index("</main>")
    for modal_id in ("review-modal", "problem-modal", "cmdk"):
        assert html.index(f'id="{modal_id}"') > main_end, f"{modal_id} 가 main 안에 있다"


def test_modal_a11y_is_shared_not_duplicated():
    """Esc·포커스 트랩·복원 규약을 모달마다 복제하면 새 모달에서 또 빠진다."""
    shared = (_JS_DIR / "modal-a11y.js").read_text(encoding="utf-8")
    assert "registerModal" in shared and "Escape" in shared and "Tab" in shared
    for name in ("history.js", "problem-modal.js", "command-palette.js"):
        src = (_JS_DIR / name).read_text(encoding="utf-8")
        assert "registerModal(" in src, f"{name} 이 공통 모듈을 쓰지 않는다"


def test_problem_modal_has_a_height_ceiling(css):
    """상한이 없으면 박스가 문제문 길이만큼 자란다.

    `.pm-left`/`.pm-right` 든 `.pm-box` 든 어딘가에는 상한이 있어야 한다. 없으면
    `.pm-body{overflow:hidden}` 과 두 열의 `overflow-y:auto` 가 전부 무효가 되고
    (scrollHeight == clientHeight), 헤더가 화면 밖으로 스크롤된다.
    """
    # 줄 시작으로 앵커한다 — 앵커가 없으면 공유 규칙(`.modal-box, .pm-box {`)을 먼저 잡는다.
    box = re.search(r"^\.pm-box\s*\{([^}]*)\}", css["surfaces.css"], re.M)
    assert box, ".pm-box 규칙이 없다"
    assert re.search(r"max-height:", box.group(1)), ".pm-box 에 높이 상한이 없다"
    # 두 열은 스스로 상한을 갖지 않는다 — flex 가 배분해야 내부 스크롤이 동작한다.
    for col in (".pm-left", ".pm-right"):
        rule = re.search(re.escape(col) + r"\s*\{([^}]*)\}", css["surfaces.css"])
        assert rule and "min-height: 0" in rule.group(1), f"{col} 에 min-height:0 이 없다"


def test_row_activation_does_not_swallow_child_control_keys(js):
    """행 안의 링크·버튼은 자기 동작을 해야 한다.

    `makeRowActivatable` 의 keydown 핸들러가 preventDefault 를 무조건 부르면 앵커의
    기본 활성화까지 취소된다 — 링크에 포커스한 채 Enter 를 눌러도 문제 페이지가 열리지
    않고 행 모달이 열린다(WCAG 2.1.1 위반).
    """
    src = js["utils.js"]
    fn = re.search(r"function makeRowActivatable[\s\S]*?\n\}", src)
    assert fn, "makeRowActivatable 이 없다"
    body = fn.group(0)
    # click·keydown 양쪽에서 자식 대화형 요소를 걸러야 한다.
    assert body.count("closest('a, button')") >= 1 or body.count('closest("a, button")') >= 1
    assert body.count("fromChildControl(e)") >= 2, "click·keydown 양쪽에 가드가 필요하다"
    # 인라인 핸들러로 우회하면 안 된다 — 위임 리스너가 유일한 배선이어야 한다.
    assert "onclick=" not in js["history.js"], "인라인 onclick 이 남아 있다"


def test_every_async_render_path_checks_its_generation_token(js):
    """세대 토큰은 성공·실패 **양쪽** 경로에 있어야 한다.

    성공 경로만 막고 catch 에 가드가 없으면, A 를 닫고 B 를 연 뒤 A 의 요청이 실패했을 때
    B 의 스피너 자리에 A 의 오류가 그려진다. 한 곳만 비대칭이면 규약이 아니다.

    토큰을 쓰는 함수만 본다. 경쟁이 없는 다른 async 함수까지 요구하면 거짓 빨강이 난다
    (테마 목록 로딩처럼 선택 상태에 묶이지 않는 경로가 있다).
    """
    guarded = [
        ("problem-modal.js", "async function openProblemModal", r"_currentProblem\?\.ref !== ref"),
        ("tier-chart.js", "async function loadTierChart", r"token !== _chartToken"),
        ("themes.js", "async function loadThemeProblems", r"token !== _themeToken"),
        ("stats.js", "async function loadStats", r"token !== _statsToken"),
        ("history.js", "async function loadHistory", r"token !== _historyToken"),
        ("history.js", "async function openReviewModal", r"token !== _modalToken"),
        ("command-palette.js", "async function searchProblems", r"token !== _paletteToken"),
        ("command-palette.js", "async function showLedger", r"token !== _paletteToken"),
    ]
    for name, signature, pattern in guarded:
        body = _js_function_body(js[name], signature)
        assert re.search(pattern, body), f"{name}:{signature} 에 세대 가드가 없다"
        # catch 블록 안에도 있어야 한다 — 늦은 **실패**가 새 화면을 덮는 경로다.
        catch_body = _js_function_body(body[body.index("catch"):], "catch")
        assert re.search(pattern, catch_body), (
            f"{name}:{signature} 의 catch 에 세대 가드가 없다 — 늦은 실패가 새 화면을 덮는다")

    # report.js 는 화살표 함수 핸들러라 시그니처로 자를 수 없다 — 파일 단위로 확인한다.
    assert js["report.js"].count("token !== _reportToken") >= 2, (
        "report.js 의 성공·실패 경로 중 한쪽에 세대 가드가 없다")


def test_history_load_is_not_assumed_to_be_single_flight(js):
    """`loadHistory` 는 버튼 외에 탭 전환·재리뷰 완료에서도 불린다 — 버튼 disabled 를
    단일 호출의 근거로 삼을 수 없다."""
    src = js["history.js"]
    body = _js_function_body(src, "async function loadHistory")
    assert re.search(r"const token = \+\+_historyToken", body)
    # finally 가 무조건 복원하면 무효화된 옛 실행이 진행 중 실행의 버튼을 되살린다.
    finally_block = body.split("finally", 1)[1]
    assert re.search(r"token === _historyToken", finally_block)
    # 호출처가 셋이라는 사실 자체를 고정한다.
    assert "loadHistory()" in js["tabs.js"], "탭 전환 호출이 사라지면 이 규약의 근거가 바뀐다"


def test_modal_recovers_focus_that_escapes_to_the_body(js):
    """포커스를 가진 요소가 disabled 되거나 사라지면 브라우저가 포커스를 <body> 로 옮긴다.

    모달 안에서 그러면 keydown 리스너가 root 에 걸려 있어 Esc·Tab 트랩이 함께 죽는다
    (setLoading 이 10~20초짜리 작업에서 실제로 그렇게 만든다).
    """
    src = js["modal-a11y.js"]
    assert re.search(r"addEventListener\(['\"]focusout['\"]", src), "포커스 이탈 감시가 없다"
    # root 가 마지막 수단으로 포커스를 받으려면 tabindex 가 있어야 한다.
    assert re.search(r"root\.tabIndex\s*=\s*-1", src), \
        "tabindex 없이 root.focus() 는 조용히 무효다"


def test_timestamps_are_rendered_in_the_viewers_timezone(js):
    """저장값은 UTC 다 — 문자열을 그냥 자르면 한국 00:00~09:00 제출이 전날로 찍힌다.

    같은 제출이 GitHub README(KST 로 변환)와 다른 날짜가 되는 조용한 오답이고,
    성장 곡선의 날짜 그룹도 함께 어긋난다.
    """
    # 위반 코드는 템플릿 리터럴 안에 있어 _code_lines 로는 보이지 않는다(그 헬퍼는 `${}`
    # 내용을 줄에 담지 않는다). 원본을 훑되 주석 줄만 걸러 낸다.
    for name, src in js.items():
        for lineno, raw in enumerate(src.splitlines(), 1):
            stripped = raw.strip()
            if stripped.startswith("//") or stripped.startswith("*"):
                continue
            assert not re.search(r"(created_at|last_submitted|imported_at)[^;\n]*slice\(\s*0",
                                 raw), \
                f"{name}:{lineno} 이 시각 문자열을 잘라 쓴다 — localDate() 를 거쳐야 한다"

    # 부정 단정만 있으면 표시를 통째로 지워도 통과한다 — 변환기의 존재와 규칙도 고정한다.
    body = _js_function_body(js["utils.js"], "function parseStoredTime")
    assert re.search(r"const hasZone\s*=", body), "오프셋 유무 판정이 없다"
    # 판정만 있고 쓰지 않으면 규칙이 죽는다 — JS 는 오프셋 없는 ISO 를 **로컬 시각**으로
    # 읽으므로(ES2015+), Date 생성에 그 분기가 반영되어야 UTC 로 읽힌다.
    assert re.search(r"new Date\([^)]*hasZone[^)]*\)", body), \
        "오프셋이 없을 때 UTC 로 읽는 분기가 Date 생성에 반영되지 않았다"
    assert re.search(r"function localDate\(", js["utils.js"])
    for name in ("history.js", "import-history.js", "tier-chart.js",
                 "stats.js", "command-palette.js", "load-submission.js"):
        assert "localDate(" in js[name], f"{name} 이 날짜를 변환 없이 그린다"


def test_tier_filter_is_boj_only(js):
    """난이도 그룹 경계는 solved.ac 티어 1~30 체계다. CF 행은 tier 가 항상 0 이라
    플랫폼을 보지 않으면 'Unrated' 선택에 CF 문제가 전량 딸려 온다."""
    # 그룹 경계의 정의는 utils.js 한 곳에만 둔다 — 서버가 같은 표를 또 가지면 두 벌이 갈린다.
    assert re.search(r"function tierGroupParams\(key\)", js["utils.js"])
    body = _js_function_body(js["utils.js"], "function tierGroupParams")
    assert re.search(r"platform:\s*['\"]boj['\"]", body), \
        "난이도 그룹을 고르면 platform 을 boj 로 고정해야 한다"
    assert "TIER_GROUPS[key]" in body, "경계는 TIER_GROUPS 한 곳에서만 읽는다"
    for name in ("history.js", "import-history.js"):
        assert "tierGroupParams(" in js[name], f"{name} 이 그룹을 서버 질의로 풀지 않는다"


def _global_function_owners() -> dict[str, str]:
    """전역에서 호출 가능한 함수 이름 → 정의한 파일.

    최상위 `function` 선언과 `window.NAME = ` 노출을 모두 센다 — modal-a11y 처럼 IIFE 안에서
    정의하고 window 로 내보내는 파일이 있다.
    """
    owners = {}
    for path in sorted(_JS_DIR.glob("*.js")):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r"^(?:async\s+)?function\s+([A-Za-z_$][\w$]*)", src, re.M):
            owners[m.group(1)] = path.name
        for m in re.finditer(r"window\.([A-Za-z_$][\w$]*)\s*=", src):
            owners[m.group(1)] = path.name
    return owners


# `/` 앞에 이 토큰이 오면 정규식 리터럴의 시작이다(나눗셈이 아니다). `=>` 의 `>` 가
# 빠지면 `s => /\{/.test(s)` 의 정규식을 나눗셈으로 읽어 본문의 중괄호를 코드로 센다.
_REGEX_PRECEDERS = "(,=:[!&|?{};+-*%~^<>"
_REGEX_KEYWORDS = ("return", "typeof", "case", "in", "of", "new", "do", "else", "yield", "await")
# 이 키워드로 시작하는 블록은 **로드 시점에 실행된다**. 함수·객체·클래스 본문과 달리
# 나중에 불리는 게 아니라 그 자리에서 돈다.
_CONTROL_BLOCK = re.compile(
    r"^(?:\}\s*)?(?:if|else|for|while|switch|try|catch|finally|do)\b|^\{$")


def _code_lines(src: str, unterminated: list | None = None) -> list[tuple[int, str, bool]]:
    """(그 줄 시작 시점의 중괄호 깊이, 리터럴·주석을 지운 줄, 로드 시점 실행 여부) 목록.

    문자열·템플릿 리터럴·정규식·주석은 **파일 전체를 문자 스트림으로** 훑으며 지운다.
    줄 단위로 처리하면 여러 줄에 걸친 템플릿 리터럴의 내부 중괄호가 코드로 세어져
    깊이 카운터가 고착되고, 그 뒤 파일 전체가 검사에서 조용히 빠진다.

    템플릿 리터럴의 `${...}` 는 코드로 되돌아가 훑는다 — 그 안에 또 템플릿이 오는 형태가
    실제로 쓰이므로(`history.js`·`import-history.js`), 안쪽 백틱을 바깥 리터럴의 종료로
    읽으면 그 뒤 전체가 어긋난다. `${}` 안의 문자는 최상위 실행문이 될 수 없어 줄 내용에는
    담지 않지만, **정규식/나눗셈 판별용 문맥에는 담는다** — 담지 않으면 `${a / b}` 의 `/`
    앞이 빈 문자열로 보여 정규식으로 오독되고 그 뒤 깊이가 통째로 어긋난다.

    세 번째 값은 "이 줄이 로드 시점에 실행되는가" 다. 중괄호마다 그것을 연 것이 제어
    블록(`if`·`try`·`for` …)인지 함수·객체·클래스인지 기록해, 제어 블록만 거쳐 온 줄은
    깊이가 0 이 아니어도 로드 시점 실행으로 본다.
    """
    if not src.endswith("\n"):
        src += "\n"          # 마지막 줄의 시작 깊이가 아니라 **끝난 뒤** 깊이를 보게 한다

    out: list[tuple[int, str, bool]] = []
    depth = 0
    line_start_depth = 0
    buf: list[str] = []                 # 이 줄의 코드 문자(${} 안은 제외)
    ctx: list[str] = []                 # 정규식 판별용 문맥(${} 안 포함, 줄을 넘어 이어진다)
    brace_is_control: list[bool] = []    # 각 중괄호를 연 것이 제어 블록인가
    line_start_control = True
    stack: list[tuple[str, int]] = []   # ('tpl', 0) 템플릿 텍스트 / ('sub', 진입 깊이) ${} 안
    i = 0
    n = len(src)

    def note(ch: str) -> None:
        ctx.append(ch)
        if len(ctx) > 16:
            del ctx[0]

    def all_control() -> bool:
        return all(brace_is_control)

    def flush():
        nonlocal line_start_depth, line_start_control
        out.append((line_start_depth, "".join(buf).strip(), line_start_control))
        buf.clear()
        line_start_depth = depth
        line_start_control = all_control()

    while i < n:
        ch = src[i]

        if stack and stack[-1][0] == "tpl":
            if ch == "\\":
                i += 2
                continue
            if ch == "\n":
                flush()
                i += 1
                continue
            if ch == "`":
                stack.pop()
                i += 1
                continue
            if ch == "$" and i + 1 < n and src[i + 1] == "{":
                stack.append(("sub", depth))
                # `${` 는 식의 시작이다 — 바로 뒤의 `/` 는 나눗셈이 아니라 정규식이다.
                note("{")
                i += 2
                continue
            i += 1
            continue

        in_subst = bool(stack) and stack[-1][0] == "sub"

        if ch == "\n":
            flush()
            i += 1
            continue

        if ch == "/" and i + 1 < n and src[i + 1] == "/":
            while i < n and src[i] != "\n":
                i += 1
            continue
        if ch == "/" and i + 1 < n and src[i + 1] == "*":
            end_at = src.find("*/", i + 2)
            block = src[i:(end_at + 2) if end_at != -1 else n]
            for _ in range(block.count("\n")):
                flush()
            i = (end_at + 2) if end_at != -1 else n
            continue

        if ch == "`":
            stack.append(("tpl", 0))
            note("`")
            i += 1
            continue
        if ch in "\"'":
            quote = ch
            i += 1
            while i < n:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "\n":
                    # 줄을 넘는 따옴표 문자열은 JS 에서 SyntaxError 다 — 호출부가 요청하면 알린다.
                    if unterminated is not None:
                        unterminated.append(len(out) + 1)
                    break
                if src[i] == quote:
                    i += 1
                    break
                i += 1
            note(quote)
            continue

        if ch == "/":
            before = "".join(ctx).rstrip()
            if (not before or before[-1] in _REGEX_PRECEDERS
                    or before.endswith(_REGEX_KEYWORDS)):
                i += 1
                in_class = False
                while i < n and src[i] != "\n":
                    if src[i] == "\\":
                        i += 2
                        continue
                    if src[i] == "[":
                        in_class = True
                    elif src[i] == "]":
                        in_class = False
                    elif src[i] == "/" and not in_class:
                        i += 1
                        break
                    i += 1
                note("/")
                continue

        if ch == "{":
            head = "".join(buf).strip() if not in_subst else ""
            brace_is_control.append(bool(_CONTROL_BLOCK.match(head)))
            depth += 1
        elif ch == "}":
            if in_subst and depth == stack[-1][1]:
                stack.pop()                    # ${...} 가 닫혔다 — 템플릿 텍스트로 되돌아간다
                note("}")
                i += 1
                continue
            depth -= 1
            if brace_is_control:
                brace_is_control.pop()

        note(ch)
        if not in_subst:
            buf.append(ch)
        i += 1

    flush()
    return out


def _strip_leading_trivia(src: str) -> str:
    """파일 앞의 공백·주석을 걷어낸 나머지."""
    i = 0
    n = len(src)
    while i < n:
        if src[i].isspace():
            i += 1
        elif src.startswith("//", i):
            nl = src.find("\n", i)
            i = n if nl == -1 else nl + 1
        elif src.startswith("/*", i):
            end_at = src.find("*/", i + 2)
            i = n if end_at == -1 else end_at + 2
        else:
            break
    return src[i:]


def _is_iife_module(src: str) -> bool:
    """파일 **전체**가 `(function () { ... })();` 한 겹으로 감싸여 있는지.

    선두·말미만 보면 `(function(){…})(); run(); (function(){…})();` 같은 샌드위치가
    통과한다. 그러면 base 가 1 이 되어 가운데의 진짜 최상위 실행문이 통째로 검사에서
    빠진다. 그래서 중간에 깊이가 0 으로 돌아오는 줄이 있는지도 확인한다.
    """
    body = _strip_leading_trivia(src)
    if not re.match(r"\(function\s*\(\s*\)\s*\{", body):
        return False
    if not body.rstrip().rstrip(";").rstrip().endswith(("})()", "}())")):
        return False
    lines = _code_lines(body)
    return not any(depth == 0 and stripped for depth, stripped, _ in lines[1:-1])


def _strip_deferred_bodies(text: str) -> str:
    """화살표·function 본문을 지운다 — 그 안의 호출은 로드 시점에 실행되지 않는다.

    `=>` 를 만나면 본문 끝까지 건너뛴다. 중괄호 본문이면 균형이 맞을 때까지, 식 본문이면
    같은 괄호 깊이의 `,` 나 닫는 괄호까지다. 첫 `=>` 에서 줄 전체를 버리면 그 뒤의 즉시
    호출까지 사라진다(`{ on: () => 1, init: f() }` 의 `f`).
    """
    out = []
    i = 0
    n = len(text)
    depth = 0            # () 와 [] 깊이
    while i < n:
        if text.startswith("=>", i) or re.match(r"\bfunction\b", text[i:]):
            i += 2 if text.startswith("=>", i) else len("function")
            while i < n and text[i] == " ":
                i += 1
            if i < n and text[i] == "{":
                brace = 0
                while i < n:
                    if text[i] == "{":
                        brace += 1
                    elif text[i] == "}":
                        brace -= 1
                        if brace == 0:
                            i += 1
                            break
                    i += 1
            else:
                start_depth = depth
                while i < n:
                    if text[i] in "([":
                        depth += 1
                    elif text[i] in ")]":
                        if depth == start_depth:
                            break
                        depth -= 1
                    elif text[i] == "," and depth == start_depth:
                        break
                    i += 1
            continue
        if text[i] in "([":
            depth += 1
        elif text[i] in ")]":
            depth -= 1
        out.append(text[i])
        i += 1
    return "".join(out)


def _load_time_calls_in(stripped: str) -> set[str]:
    """한 줄에서 **로드 시점에 실행되는** 호출 이름.

    선언문도 초기화식은 로드 시점에 평가된다 — `const X = helperFromAnotherFile();` 는
    로드 순서에 의존한다. 화살표·함수 본문 안의 호출은 나중에 실행되므로 그 부분만 지운다.
    `class A extends f() {}` 의 `f()` 도 로드 시점 호출이라 `extends` 뒤를 본다.
    """
    if stripped.startswith(("}", ")")):
        return set()
    if stripped.startswith("class"):
        _, sep, tail = stripped.partition("extends")
        if not sep:
            return set()
        stripped = tail.split("{", 1)[0]
    elif re.match(r"(?:async\s+)?function\b", stripped):
        return set()
    elif re.match(r"(?:const|let|var)\b", stripped):
        _, sep, init = stripped.partition("=")
        if not sep:
            return set()
        stripped = init
    return set(re.findall(r"\b([A-Za-z_$][\w$]*)\s*\(", _strip_deferred_bodies(stripped)))


def _top_level_calls(src: str, name: str = "") -> set[str]:
    """로드 시점에 실행되는 줄에서 호출하는 함수 이름.

    깊이가 최상위인 실행문과, **제어 블록만 거쳐 온** 줄을 본다 — 최상위 `if (x) { f(); }`
    의 `f()` 는 로드 시점에 실행되므로 로드 순서에 의존한다. 함수·객체·클래스 본문 안의
    호출은 나중에 실행되므로 제외된다. IIFE 로 감싼 파일은 래퍼 본문 전체가 로드 시점
    실행이므로 깊이 1 을 최상위로 본다.

    알려진 경계: 한 줄에 다 담긴 핸들러(`el.onclick = () => f();`)의 `f` 는 지워지지만,
    줄 단위로 보므로 여러 줄 핸들러의 본문은 깊이로 걸러진다.
    """
    lines = _code_lines(src)
    base = 1 if _is_iife_module(src) else 0
    # 마지막 항목의 시작 깊이 = 스트림을 다 훑은 뒤의 깊이. 0 이 아니면 리터럴·주석
    # 처리가 어딘가에서 깨져 그 지점 이후를 검사하지 못한다.
    final_depth = lines[-1][0]
    assert final_depth == 0, (
        f"{name or 'JS'}: 중괄호 균형이 {final_depth} 로 끝났다 — 리터럴 처리가 깨져 "
        f"이 파일의 로드 시점 호출을 검사하지 못한다")

    calls = set()
    for depth, stripped, load_time in lines:
        if not stripped or depth < base:
            continue
        if depth != base and not load_time:
            continue
        calls.update(_load_time_calls_in(stripped))
    return calls


def test_script_load_order_satisfies_load_time_dependencies(html):
    """소비자보다 정의가 먼저 실려야 한다 — **로드 시점에 실행되는 호출**에 한해서.

    빌드 스텝이 없어 index.html 의 `<script>` 순서가 곧 평가 순서다. 순서가 뒤집히면
    소비 시점에 ReferenceError 가 나고, 그 스크립트의 **그 줄 이후만** 조용히 배선되지
    않는다(앞부분은 이미 실행돼 있어 화면상 정상으로 보인다).

    이벤트 핸들러 안의 호출은 이 계약과 무관하다 — 그때는 모든 스크립트가 이미 평가됐다.
    """
    order = {name: i for i, name in
             enumerate(re.findall(r"js/([a-z0-9-]+\.js)\?v=", html))}
    owners = _global_function_owners()

    violations = []
    for path in sorted(_JS_DIR.glob("*.js")):
        consumer = path.name
        for name in _top_level_calls(path.read_text(encoding="utf-8"), consumer):
            provider = owners.get(name)
            if not provider or provider == consumer:
                continue
            assert provider in order, f"{provider} 가 index.html 에 없다"
            assert consumer in order, f"{consumer} 가 index.html 에 없다"
            if order[provider] > order[consumer]:
                violations.append(
                    f"{consumer} 가 로드 시점에 {name}() 를 부르는데 "
                    f"정의 파일 {provider} 이 뒤에 실린다")
    assert not violations, "스크립트 로드 순서:\n  " + "\n  ".join(violations)


def test_the_load_order_check_sees_every_known_dependency(html):
    """검사가 실제로 무엇을 보고 있는지 못박는다.

    "빈 집합이 아니다" 만 확인하면 추출기가 일부 파일을 놓쳐도 통과한다 — 알려진 의존을
    이름으로 고정해 두면 그 파일이 사각지대가 되는 순간 빨강이 난다.
    IIFE 로 감싼 모듈(command-palette)은 래퍼 한 겹을 벗겨야 보인다.
    """
    owners = _global_function_owners()
    assert owners.get("registerModal") == "modal-a11y.js"
    cross = {
        (p.name, name)
        for p in sorted(_JS_DIR.glob("*.js"))
        for name in _top_level_calls(p.read_text(encoding="utf-8"), p.name)
        if owners.get(name) and owners[name] != p.name
    }
    expected = {
        ("history.js", "registerModal"),
        ("problem-modal.js", "registerModal"),
        ("command-palette.js", "registerModal"),
    }
    assert expected <= cross, f"검사가 놓친 의존: {sorted(expected - cross)}"


@pytest.mark.parametrize("path", sorted(_JS_DIR.glob("*.js")), ids=lambda p: p.name)
def test_the_load_order_check_can_see_into_every_file(path):
    """어느 파일도 게이트의 사각지대가 아니다.

    파일마다 최상위 호출을 하나 주입해 게이트가 그것을 보는지 확인한다. 이 확인이 없으면
    추출기가 한 파일을 통째로 못 보게 되어도 아무것도 빨강이 나지 않는다 — `_is_iife_module`
    파일 중간의 내부 IIFE 에 걸리면 그 파일이 깊이 1 기준으로 읽혀 통째로 빠진다.
    """
    src = path.read_text(encoding="utf-8")
    base_calls = _top_level_calls(src, path.name)
    if _is_iife_module(src):
        # 래퍼 안쪽 끝에 주입한다 — 래퍼 본문이 그 파일의 로드 시점 실행이다.
        closer = max(src.rfind("})()"), src.rfind("}())"))
        assert closer != -1, f"{path.name}: IIFE 판정인데 닫는 형태를 찾지 못했다"
        injected = src[:closer] + "\n  __probeMarker__();\n" + src[closer:]
    else:
        injected = src + "\n__probeMarker__();\n"
    assert "__probeMarker__" in _top_level_calls(injected, path.name), \
        f"{path.name}: 최상위 호출이 게이트에 보이지 않는다(기존 검출 {len(base_calls)}개)"


@pytest.mark.parametrize("path", sorted(_JS_DIR.glob("*.js")), ids=lambda p: p.name)
def test_handler_bodies_stay_out_of_the_load_order_check(path):
    """이벤트 핸들러 **본문** 안의 호출은 로드 순서와 무관하다 — 세면 거짓 빨강이 난다.

    깊이는 줄 단위로 본다. 한 줄에 다 담긴 핸들러(`el.onclick = () => f();`)는 최상위
    줄이라 걸러지지 않는다 — 이 레포의 핸들러는 전부 여러 줄이고, 줄 안까지 파싱하려면
    본격적인 JS 파서가 필요하다. 그 경계를 여기 명시해 둔다.
    """
    src = path.read_text(encoding="utf-8")
    injected = src + ("\ndocument.addEventListener('x', () => {\n"
                      "  __handlerMarker__();\n});\n")
    assert "__handlerMarker__" not in _top_level_calls(injected, path.name)


def test_only_whole_file_wrappers_count_as_iife_modules():
    """파일 중간의 IIFE 는 래퍼가 아니다.

    `re.M` 로 아무 줄머리나 맞히면 내부 IIFE 에도 걸려 base 가 1 이 되고, 그 파일의 진짜
    최상위 실행문이 검사에서 통째로 빠진다.
    """
    assert _is_iife_module("(function () {\n  run();\n})();\n")
    assert _is_iife_module("// 설명\n/* 블록 */\n(function () {\n  run();\n}());\n")
    assert not _is_iife_module("run();\n(function () {\n  inner();\n})();\n")
    assert not _is_iife_module("(function () {\n  inner();\n})();\nrun();\n")


@pytest.mark.parametrize("src", [
    # 파이썬 소스에도 JS 소스에도 백슬래시가 그대로 남아야 하므로 raw 문자열을 쓰고,
    # 줄바꿈만 이어붙인다. 일반 문자열에 쓰면 `\{` 가 유효하지 않은 이스케이프가 된다.
    r"const f = s => /\{/.test(s);" "\n",                 # 화살표 뒤 정규식
    "const h = a => (a / 2) + (a/3);\n",                          # 나눗셈
    r"""const q = s => /['"]/.test(s);""" "\n",  # 따옴표를 담은 정규식
    "const t = `<div>${c ? `<b>{</b>` : ''}</div>`;\n",   # 중첩 템플릿의 홀중괄호
    "const t = `<div>${c ? `<b>}</b>` : ''}</div>`;\n",
    "const t = `${JSON.stringify({a: 1})}`;\n",                   # ${} 안의 객체 리터럴
    "const t = `\nline {\nline }\n`;\n",  # 여러 줄 템플릿
    r"const r = /a\/b{/;" "\nfoo();\n",           # 정규식 안의 이스케이프된 슬래시
    "function f(x, y) { return `${Math.round(x / y)}%`; }\n",   # ${} 안의 나눗셈
    "const pct = `${a / b}%`;\n",
    "const t = `\n  ${a / b}%\n`;\n",
    "const t = `${s.replace(/[^0-9]/g, '')}`;\n",   # ${} 안의 정규식
    "const t = `${`${a / b}`}`;\n",   # 3단 중첩
    "const t = `${/[a-z]{2}/.test(s)}`;\n",   # ${} 첫 토큰이 정규식
    r"const t = `${/\{/.test(s)}`;" "\n",   # ${} 첫 토큰이 홀중괄호 정규식
    "const t = `${x}${/[0-9]{3}/.test(s)}`;\n",
])
def test_the_literal_scanner_keeps_brace_balance(src):
    """유효한 JS 에서 깊이 카운터가 어긋나면 안 된다.

    어긋나면 `_top_level_calls` 의 단정이 "리터럴 처리가 깨졌다" 라는, 원인과 무관한
    메시지로 스위트 전체를 빨강으로 만든다(거짓 빨강).
    """
    assert _code_lines(src)[-1][0] == 0


def test_a_sandwich_of_iifes_is_not_a_whole_file_wrapper():
    """선두·말미만 보면 샌드위치가 래퍼로 오인된다 — base 가 1 이 되어 가운데의 진짜
    최상위 실행문이 통째로 검사에서 빠진다."""
    sandwich = "(function () { const a = 1; })();\nrun();\n(function () { const b = 2; })();\n"
    assert not _is_iife_module(sandwich)

    src = (_JS_DIR / "utils.js").read_text(encoding="utf-8")
    wrapped = ("(function () { const _head = 1; })();\n" + src
               + "\n__probeMarker__();\n(function () { const _tail = 1; })();\n")
    assert not _is_iife_module(wrapped)
    assert "__probeMarker__" in _top_level_calls(wrapped, "utils.js")


@pytest.mark.parametrize("shape,tail", [
    ("평문", "\n__probeMarker__();\n"),
    ("if 블록", "\nif (window.x) {\n  __probeMarker__();\n}\n"),
    ("else 블록", "\nif (window.x) {\n  noop();\n} else {\n  __probeMarker__();\n}\n"),
    ("try 블록", "\ntry {\n  __probeMarker__();\n} catch (e) { noop(); }\n"),
    ("catch 블록", "\ntry {\n  noop();\n} catch (e) {\n  __probeMarker__();\n}\n"),
    ("for 블록", "\nfor (const x of []) {\n  __probeMarker__();\n}\n"),
    ("화살표 뒤 즉시 호출", "\nconst h = { on: () => 1, init: __probeMarker__() };\n"),
    ("class extends", "\nclass A extends __probeMarker__() {}\n"),
    ("삼항", "\nconst v = cond ? __probeMarker__() : 0;\n"),
    ("구조분해", "\nconst { a } = __probeMarker__();\n"),
])
def test_load_time_calls_are_seen_in_every_shape(shape, tail):
    """로드 시점에 실행되는 형태는 전부 게이트에 보여야 한다.

    최상위 `if (x) { f(); }` 의 `f()` 는 깊이가 1 이지만 **로드 시점에 실행된다** —
    깊이만으로 걸러내면 진짜 로드 순서 위반이 통과한다.
    """
    src = (_JS_DIR / "utils.js").read_text(encoding="utf-8") + tail
    assert "__probeMarker__" in _top_level_calls(src, "utils.js"), shape


@pytest.mark.parametrize("shape,tail", [
    ("여러 줄 핸들러", "\ndocument.addEventListener('x', () => {\n  __probeMarker__();\n});\n"),
    ("함수 선언 본문", "\nfunction later() {\n  __probeMarker__();\n}\n"),
    ("함수 표현식 본문", "\nconst later = function () {\n  __probeMarker__();\n};\n"),
    ("화살표 본문", "\nconst later = () => {\n  __probeMarker__();\n};\n"),
    ("한 줄 화살표", "\nconst later = () => __probeMarker__();\n"),
])
def test_deferred_calls_stay_out_of_the_load_order_check(shape, tail):
    """나중에 실행되는 호출은 로드 순서와 무관하다 — 세면 거짓 빨강이 난다."""
    src = (_JS_DIR / "utils.js").read_text(encoding="utf-8") + tail
    assert "__probeMarker__" not in _top_level_calls(src, "utils.js"), shape


def test_a_file_without_a_trailing_newline_still_balances():
    """마지막 항목의 시작 깊이가 아니라 **끝난 뒤** 깊이를 봐야 한다.

    개행 없이 `}` 로 끝나면 그 줄의 시작 깊이는 1 이라, 정상 파일이 "리터럴 처리가
    깨졌다" 는 원인과 무관한 메시지로 스위트를 빨강으로 만든다.
    """
    for path in sorted(_JS_DIR.glob("*.js")):
        src = path.read_text(encoding="utf-8").rstrip("\n")
        assert _code_lines(src)[-1][0] == 0, path.name


def test_fetch_json_ok_actually_checks_the_response_status(js):
    """`fetchJsonOk` 안에서 res.ok 를 보는지 못박는다.

    "원시 fetch 를 쓰지 않는다" 만 검사하면 이 한 줄을 지워도 전부 초록이다 — 그러면
    503(온디맨드 DB 정지)이 빈 배열로 해석돼 '기록이 없습니다' 로 표시된다.
    """
    body = _js_function_body(js["utils.js"], "async function fetchJsonOk")
    assert re.search(r"!\s*res\s*\.\s*ok", body), "res.ok 검사가 없다"
    assert re.search(r"throw\s+new\s+Error", body), "실패를 예외로 올리지 않는다"


def test_error_detail_handles_the_validation_error_shape(js):
    """FastAPI 의 422 detail 은 **배열**이다 — 그대로 문자열에 넣으면 `[object Object]`."""
    body = _js_function_body(js["utils.js"], "function errorDetail")
    assert "Array.isArray" in body, "배열 detail 분기가 없다"


def _unterminated_string_lines(src: str) -> list[int]:
    """따옴표가 줄 끝까지 닫히지 않은 줄 번호.

    `_code_lines` 를 그대로 쓴다 — 정규식 리터럴 안의 따옴표(`/"/g`)와 여러 줄 템플릿
    리터럴을 이미 올바르게 다룬다. 줄 단위로 다시 세면 그 둘이 거짓 양성이 된다.
    """
    found: list[int] = []
    _code_lines(src, found)
    return found


@pytest.mark.parametrize("path", sorted(_JS_DIR.glob("*.js")), ids=lambda p: p.name)
def test_no_unterminated_string_literals(path):
    """`'…'`·`"…"` 는 줄을 넘을 수 없다 — 넘으면 그 파일 전체가 SyntaxError 다.

    로컬 게이트로는 잡히지 않는다 — node 가 없으면 구문 검사를 건너뛴다.
    """
    bad = _unterminated_string_lines(path.read_text(encoding="utf-8"))
    assert not bad, f"{path.name}: {bad} 번 줄의 문자열이 줄 끝까지 닫히지 않았다"
