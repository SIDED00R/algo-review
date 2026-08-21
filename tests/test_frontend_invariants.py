"""프론트엔드 불변식 (회귀).

빌드 스텝이 없어 JS 배선 끊김을 잡는 자동 방어선이 문자열 수준 검사뿐이다. 정확 문자열 대신
**정규식**으로 쓴다 — 공백·인용부호·줄바꿈이 바뀌면 거짓 빨강이 나고, 그 때문에 검사를
느슨하게 만들면 거짓 초록이 된다.

여기 고정하는 것은 전부 "고쳐 놓으면 조용히 되돌아가는" 성질의 결함이다.
"""
import re
from pathlib import Path

import pytest

_JS_DIR = Path(__file__).resolve().parent.parent / "static" / "js"
# 전 파일을 읽는다. 예전에는 10개만 고정해 두고 "전 파일에서 원시 fetch 를 막는다" 같은
# 검사가 그 목록만 순회했다 — 나머지 10개(command-palette·themes·load-submission 등)는
# 무엇을 넣어도 초록이었다.
_MIN_JS_FILES = 20


def _js_function_body(src, signature):
    """`signature` 로 시작하는 함수의 본문을 중괄호 균형으로 잘라낸다.

    문자 수 윈도우로 찾으면 함수에 한두 줄만 추가돼도 "호출이 사라졌다"는 틀린 메시지로
    빨강이 난다(실측 여유가 41자·137자밖에 없었다). 이 파일 docstring 이 경계하는 패턴이다.
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

    예전에는 결과 노드가 사라졌을 때 catch 안에서 같은 null 을 다시 참조해 예외가 함수를
    탈출하고, 버튼이 disabled + '실행 중...' 으로 영구 고착됐다(새로고침 외 복구 불가).
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
    """사라진 노드에 쓰면 안 된다 — outerHTML 직접 대입이 남아 있으면 회귀다."""
    src = js["problem-modal.js"]
    assert not re.search(r"document\.getElementById\(tcId\)\.outerHTML", src), \
        "노드 존재 확인 없이 outerHTML 에 대입하면 안 된다"
    assert re.search(r"const\s+cell\s*=\s*document\.getElementById\(tcId\)[\s\S]{0,120}?if\s*\(cell\)", src)


def test_all_fill_review_form_entry_points_confirm_overwrite():
    """진입점 넷이 같은 규약을 따라야 한다.

    예전에는 이름만 "넷" 이고 뷰어 경로 하나만 검사해서, 나머지 세 곳에서 확인 호출을
    지워도 초록이었다(편집 중 코드를 경고 없이 덮어쓰는 회귀).
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
        # 파일 어딘가에 각각 1회면 통과하던 검사였다 — 확인이 **호출보다 앞에** 있는지 본다.
        guard = re.search(r"if\s*\(!confirmEditorOverwrite\(\)\)\s*return", src)
        assert guard, f"{name}({label}) 이 덮어쓰기 확인을 건너뛴다"
        # 정의(`function fillReviewForm(`)는 호출이 아니다 — load-submission.js 는
        # 로더를 정의하면서 자기 버튼에서 호출도 한다.
        call = re.search(r"(?<!function )\bfillReviewForm\(", src)
        assert call, f"{name}({label}) 에 fillReviewForm 호출이 없다"
        assert guard.start() < call.start(), (
            f"{name}({label}) 에서 덮어쓰기 확인이 fillReviewForm 호출보다 뒤에 있다")


def test_imported_review_updates_the_list_data_not_just_the_dom(js):
    """서버가 행을 실제로 삭제하므로 목록 데이터에서도 빼야 한다.

    예전에는 함수가 톱레벨에 있어 allProblems 에 접근할 수 없었고, 필터를 한 번 만지면
    삭제된 항목이 되살아났다(재클릭 시 404).
    """
    src = js["import-history.js"]
    assert not re.search(r"^async function requestImportedReview", src, re.M), \
        "톱레벨에 있으면 allProblems 클로저에 접근할 수 없다"
    assert re.search(r"^  async function requestImportedReview", src, re.M)
    assert re.search(r"allProblems\.splice\(", src)


def test_tier_chart_keeps_the_first_occurrence_per_problem(js):
    """마지막 회차를 남기면 재제출이 과거 곡선을 소급 변경한다.

    tier 는 회차가 아니라 문제의 속성이라 값은 같고 날짜만 이동한다.
    """
    src = js["tier-chart.js"]
    assert ".reverse()" not in src, "reverse 하면 문제당 마지막 회차가 남는다"
    # 서버가 오름차순으로 주므로 재정렬이 필요 없다.
    assert not re.search(r"deduped\.sort\(", src)
    # 부정 단정만 있으면 dedupe 블록을 통째로 지워도 통과한다 — 구현의 존재도 고정한다.
    assert re.search(r"new Set\(", src), "문제별 중복 제거가 없다"
    assert re.search(r"if\s*\(!\s*seenPids\.has\(", src), "첫 등장 유지 판정이 없다"
    assert re.search(r"history\.forEach\(", src), "정순 1패스가 아니다"


def test_pasted_statement_wins_over_the_viewer_cache(js):
    """서버 resolve_statement 와 같은 우선순위여야 LLM 리뷰와 README 가 갈리지 않는다."""
    assert re.search(r"description:\s*pastedStatement\s*\|\|\s*cfSections", js["review.js"])


def test_markdown_rendering_falls_back_when_the_cdn_is_blocked(js):
    """CDN 이 막히면 서버가 이미 저장·과금한 리뷰 결과가 화면에서 사라졌다."""
    assert re.search(r"function\s+renderMarkdown\s*\(", js["utils.js"])
    assert re.search(r"typeof\s+marked\s*===\s*['\"]undefined['\"]", js["utils.js"])
    # 렌더 지점은 전부 헬퍼를 거쳐야 한다 — 직접 호출이 남아 있으면 그 경로만 가드가 없다.
    for name in ("history.js", "report.js", "review.js"):
        assert "marked.parse" not in js[name], f"{name} 이 marked 를 직접 부른다"
        assert "DOMPurify.sanitize" not in js[name], f"{name} 이 DOMPurify 를 직접 부른다"


def test_outage_is_not_reported_as_empty_data(js):
    """res.ok 를 안 보면 503(온디맨드 DB 정지)이 '기록이 없습니다'로 표시된다."""
    # 전 파일에서 원시 fetch 를 막고, utils.js 안의 fetchJsonOk 정의 한 곳만 예외로 둔다.
    for name, src in js.items():
        for line_no, line in enumerate(src.split("\n"), 1):
            if not re.search(r"(?<![.\w])fetch\s*\(", line):
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
    # 양성 단정을 함께 둔다 — 부정 단정만 있으면 대입을 통째로 지워도 통과했다.
    assert re.search(r"dataset\.loaded\s*=", body), "성공 경로에 loaded 표시가 없다"
    # catch 블록 안에는 없어야 한다(문자 수 윈도우 대신 중괄호 균형으로 자른다).
    catch_body = _js_function_body(body[body.index("} catch"):], "catch")
    assert "dataset.loaded" not in catch_body


def test_loading_labels_are_specific_per_button(js):
    """기본 문구가 '분석 중...' 이면 기록 불러오기·추천받기에도 그게 뜬다."""
    assert re.search(r"loadingLabel\s*\|\|\s*['\"]처리 중", js["utils.js"])
    for name in ("history.js", "stats.js"):
        assert "dataset.loadingLabel" in js[name], f"{name} 버튼에 로딩 문구가 없다"


def test_repo_select_listener_is_bound_once(js):
    """데이터 로딩 함수 안에서 리스너를 걸면 재호출 시 누적된다."""
    assert re.search(r"repoSelect\.dataset\.bound", js["github.js"])
    # try 의 닫는 괄호를 요구한다 — 그냥 `catch {}` 로 찾으면 이 결함을 설명하는
    # 주석 문구까지 걸린다(문자열 검사의 취약함이 그대로 드러나는 예다).
    assert not re.search(r"\}\s*catch\s*\{\s*\}", js["github.js"]),         "빈 catch 는 실패를 무음으로 만든다"


# ── 접근성·CSS 불변식 ──

_CSS_DIR = Path(__file__).resolve().parent.parent / "static" / "css"
_HTML = Path(__file__).resolve().parent.parent / "static" / "index.html"


def _strip_css_comments(src):
    """규칙을 찾는 검사는 주석을 봐서는 안 된다 — 결함을 설명하는 주석에 그 결함의
    코드 형태가 그대로 적혀 있어 거짓 빨강이 난다(실제로 두 번 걸렸다)."""
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

    --line/--line-strong 은 1.15~1.68:1 로 미달이었다. 배경이 지면과 1.03~1.06:1 이라
    테두리가 유일한 식별 수단인 컨트롤에만 전용 토큰을 쓴다.
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

    "GitHub 연결됨" 배지와 "효율적" 판정이 같은 토큰을 쓰던 상태를 막는다.
    --eff-* 는 판정 배지(.eff-*)와 리뷰 결과(.points-box)만 쓴다.
    """
    for name in ("components.css", "surfaces.css", "layout.css", "base.css"):
        for line_no, line in enumerate(css[name].split("\n"), 1):
            if "var(--eff-" not in line:
                continue
            allowed = line.lstrip().startswith(".eff-") or ".points-box" in line
            assert allowed, f"{name}:{line_no} 이 판정 토큰을 직접 쓴다 — {line.strip()[:70]}"


def test_javascript_does_not_consume_verdict_tokens(js):
    """CSS 만 훑으면 소비처의 절반을 못 본다 — 통계 바와 티어 차트 색은 JS 가 읽는다.

    실제로 stats.js 와 tier-chart.js 가 --eff-* 를 직접 읽고 있었고, 위 CSS 전용 검사는
    그것을 통과시켰다. 데이터 시각화는 --bar-*/--chart-line 을 쓴다(tokens.css 에서
    --eff-* 를 별칭으로 두므로 색은 같다).
    """
    for name, src in js.items():
        for line_no, line in enumerate(src.split("\n"), 1):
            assert "--eff-" not in line, (
                f"{name}:{line_no} 이 판정 토큰을 직접 읽는다 — {line.strip()[:70]}")
    assert "--chart-line" in js["tier-chart.js"], "차트가 전용 토큰을 쓰지 않는다"
    assert "--bar-high" in js["stats.js"], "통계 바가 전용 토큰을 쓰지 않는다"


def test_cmdk_input_selector_beats_the_element_selector(css):
    """input[type="text"] 는 (0,1,1) 이라 .cmdk-input (0,1,0) 을 순서와 무관하게 이긴다.

    예전에는 이 블록의 선언 6개가 전부 무효였다.
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

    두 번 틀렸다. ① `.row:first-child` — #history-list 의 첫 자식은 항상 .toolbar 라
    리뷰 기록 탭에서 매칭되지 않았다. ② `.row + .row` — 가져오기 목록은 행마다 코드 보기
    패널 div 를 형제로 끼워 넣고, 인접(+)은 DOM 구조 기준이라 display:none 형제도
    인접을 끊어 그 탭에서만 구분선이 2px 로 겹쳤다.

    일반 형제(~)는 중간 노드와 무관하게 매칭된다.
    """
    src = css["components.css"]
    assert not re.search(r"\.row:first-child", src), "구조 의존 셀렉터가 돌아왔다"
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

    예전에는 이름과 달리 #problem-statement **한 개**만 검사해서, JS 가 만드는 검색
    입력 2개와 커스텀 예제 textarea 4개가 이름 없이 남아 있어도 초록이었다.
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

    `.pm-left`/`.pm-right` 의 상한을 지우면서 `.pm-box` 에 대체 상한을 넣지 않아,
    긴 문제문에서 10,000px 이상까지 늘어났다(CDP 실측). 그러면 `.pm-body{overflow:hidden}`
    과 두 열의 `overflow-y:auto` 가 전부 무효가 되고(scrollHeight == clientHeight),
    닫기 버튼이 든 헤더가 화면 밖으로 스크롤되며 코드 에디터까지 같이 늘어난다.
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

    `makeRowActivatable` 의 keydown 핸들러가 preventDefault 로 앵커의 기본 활성화까지
    취소해, 링크에 포커스한 채 Enter 를 눌러도 문제 페이지가 열리지 않고 행 모달이
    열렸다(WCAG 2.1.1 위반). CDP 로 실제 Enter 를 주입해 확인했다.
    """
    src = js["utils.js"]
    fn = re.search(r"function makeRowActivatable[\s\S]*?\n\}", src)
    assert fn, "makeRowActivatable 이 없다"
    body = fn.group(0)
    # click·keydown 양쪽에서 자식 대화형 요소를 걸러야 한다.
    assert body.count("closest('a, button')") >= 1 or body.count('closest("a, button")') >= 1
    assert body.count("fromChildControl(e)") >= 2, "click·keydown 양쪽에 가드가 필요하다"
    # 인라인 핸들러로 우회하던 방식은 남아 있으면 안 된다.
    assert "onclick=" not in js["history.js"], "인라인 onclick 이 돌아왔다"


def test_every_async_render_path_checks_its_generation_token(js):
    """세대 토큰은 성공·실패 **양쪽** 경로에 있어야 한다.

    problem-modal.js 는 성공 경로만 막고 catch 에는 가드가 없어, A 를 닫고 B 를 연 뒤
    A 의 요청이 실패하면 B 의 스피너 자리에 A 의 오류가 그려졌다. 형제 모듈은 처음부터
    catch 에도 가드가 있었다 — 한 곳만 비대칭이면 규약이 아니다.

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
        ("command-palette.js", "async function showProblems", r"token !== _paletteToken"),
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
    assert js["report.js"].count("token !== _reportToken") >= 2,         "report.js 의 성공·실패 경로 중 한쪽에 세대 가드가 없다"


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


def test_tier_filter_is_boj_only(js):
    """난이도 그룹 경계는 solved.ac 티어 1~30 체계다. CF 행은 tier 가 항상 0 이라
    플랫폼을 보지 않으면 'Unrated' 선택에 CF 문제가 전량 딸려 온다."""
    assert re.search(r"function tierInGroup\(tier, key, platform\)", js["utils.js"])
    assert re.search(r"platform !== ['\"]boj['\"]", js["utils.js"])
    for name in ("history.js", "import-history.js"):
        assert re.search(r"tierInGroup\([^)]*p\.platform\)", js[name]), \
            f"{name} 이 플랫폼을 넘기지 않는다"
