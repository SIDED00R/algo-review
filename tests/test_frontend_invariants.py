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
_FILES = ("problem-modal.js", "import-history.js", "tier-chart.js", "review.js",
          "utils.js", "history.js", "report.js", "stats.js", "github.js", "tabs.js")


@pytest.fixture(scope="module")
def js():
    """static/js 파일 본문을 이름으로 읽는다.

    HTTP 가 아니라 디스크에서 읽는다 — 여기서 고정하는 것은 서빙 여부가 아니라 내용이고,
    자산이 실제로 서빙되는지는 test_index_assets·test_load_submission_wiring 이 본다.
    """
    out = {}
    for name in _FILES:
        path = _JS_DIR / name
        assert path.exists(), name
        out[name] = path.read_text(encoding="utf-8")
    return out


def test_run_samples_restores_the_button_in_a_finally_block(js):
    """예제 실행 루프가 어떻게 끝나든 버튼을 되돌려야 한다.

    예전에는 결과 노드가 사라졌을 때 catch 안에서 같은 null 을 다시 참조해 예외가 함수를
    탈출하고, 버튼이 disabled + '실행 중...' 으로 영구 고착됐다(새로고침 외 복구 불가).
    """
    src = js["problem-modal.js"]
    assert re.search(r"\}\s*finally\s*\{\s*(//[^\n]*\n\s*)*resetRunButton\(\)", src), \
        "runSamples 가 finally 로 버튼을 복원해야 한다"
    assert re.search(r"function\s+resetRunButton\s*\(", src)
    # 모달을 열 때·닫을 때도 진행 중인 실행을 무효화하고 버튼을 되돌린다.
    assert src.count("resetRunButton()") >= 3
    assert re.search(r"function\s+closeProblemModal[\s\S]{0,200}?resetRunButton\(\)", src)


def test_run_samples_guards_the_result_node_before_writing(js):
    """사라진 노드에 쓰면 안 된다 — outerHTML 직접 대입이 남아 있으면 회귀다."""
    src = js["problem-modal.js"]
    assert not re.search(r"document\.getElementById\(tcId\)\.outerHTML", src), \
        "노드 존재 확인 없이 outerHTML 에 대입하면 안 된다"
    assert re.search(r"const\s+cell\s*=\s*document\.getElementById\(tcId\)[\s\S]{0,120}?if\s*\(cell\)", src)


def test_all_fill_review_form_entry_points_confirm_overwrite(js):
    """진입점 넷이 같은 규약을 따라야 한다 — 뷰어 경로만 확인을 건너뛰고 있었다."""
    assert re.search(r"function\s+proceedToReview[\s\S]{0,300}?confirmEditorOverwrite\(\)",
                     js["problem-modal.js"])


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
    for name in ("tier-chart.js", "import-history.js", "history.js"):
        assert not re.search(r"await\s+fetch\(", js[name]), \
            f"{name} 은 fetchJsonOk 를 써야 한다(res.ok 검사 포함)"


def test_code_view_caches_only_successful_loads(js):
    """404 에도 loaded 를 세우면 오류 상태가 영구 캐시돼 재시도가 막힌다."""
    src = js["import-history.js"]
    # dataset.loaded 대입이 try 안의 성공 경로에만 있어야 한다 — catch 블록에는 없다.
    catch_body = src.split("코드 불러오기 실패")[1].split("catch (e)")[1][:300]
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


def test_row_hairlines_do_not_depend_on_first_child(css):
    """#history-list 의 첫 자식은 항상 .toolbar 라 :first-child 가 매칭되지 않았다."""
    src = css["components.css"]
    assert not re.search(r"\.row:first-child", src)
    assert re.search(r"\.row \+ \.row\s*\{[^}]*border-top:\s*none", src)


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
    assert html.count('tabindex="-1"') == 6 and 'aria-selected="true" aria-controls="tab-review" tabindex="0"' in html


def test_every_form_control_has_an_accessible_name(html):
    """<summary> 는 label 이 아니고 placeholder 도 접근 가능한 이름이 아니다."""
    # 문제 설명 textarea 만 이름이 없었다.
    block = html.split('id="problem-statement"')[1][:200]
    assert 'aria-label="문제 설명"' in block


def test_hints_are_linked_to_their_controls(html):
    """id 는 있는데 아무도 참조하지 않으면 스크린리더가 읽지 않는다."""
    for control, hint in (("problem-id", "problem-id-help"),
                          ("code-language", "code-language-help")):
        block = html.split(f'id="{control}"')[1][:200]
        assert f'aria-describedby="{hint}"' in block, control


def test_toggles_expose_pressed_state(html):
    assert html.count("aria-pressed") >= 4


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
