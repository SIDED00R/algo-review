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
          "utils.js", "history.js", "report.js", "stats.js", "github.js")


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
