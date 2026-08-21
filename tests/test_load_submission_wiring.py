"""HTML ↔ JS 배선 고정.

빌드 스텝이 없어서 마크업의 id 와 JS 의 참조가 어긋나도 아무것도 실패하지 않는다.
이 스위트가 그 유일한 자동 방어선이다 — 자산이 실제로 서빙되는지, 서로를 참조하는지,
그리고 조용한 오답으로 이어지는 두 지점을 문자열 수준에서 고정한다.
"""
import re

def _asset(client, path):
    res = client.get(path)
    assert res.status_code == 200, f"{path} 가 서빙되지 않는다"
    return res.text


def test_new_scripts_are_served_and_referenced(client):
    html = client.get("/").text
    for name in ("load-submission", "command-palette"):
        assert re.search(rf'src="/static/js/{name}\.js\?v=[^"]+"', html), \
            f"{name}.js 참조가 index.html 에 없다(또는 ?v= 가 빠졌다)"
        _asset(client, f"/static/js/{name}.js")


def test_load_button_markup_and_handler_agree(client):
    html = client.get("/").text
    js = _asset(client, "/static/js/load-submission.js")
    for element_id in ("load-submission-btn", "load-submission-msg", "statement-toggle"):
        assert f'id="{element_id}"' in html, f"index.html 에 #{element_id} 가 없다"
        assert element_id in js, f"load-submission.js 가 #{element_id} 를 참조하지 않는다"


def test_palette_markup_and_handler_agree(client):
    html = client.get("/").text
    js = _asset(client, "/static/js/command-palette.js")
    for element_id in ("cmdk", "cmdk-input", "cmdk-list", "cmdk-close", "cmdk-open"):
        assert f'id="{element_id}"' in html, f"index.html 에 #{element_id} 가 없다"
        assert element_id in js, f"command-palette.js 가 #{element_id} 를 참조하지 않는다"


def test_loader_always_assigns_problem_statement(client):
    """문제 설명 칸을 조건 없이 대입해야 한다.

    resolve_statement 는 요청에 본문이 있으면 무조건 그것을 쓴다. 이전 문제의 붙여넣은
    본문이 남아 있으면 다른 문제를 그 본문으로 리뷰하는 조용한 오답이 난다.
    """
    js = _asset(client, "/static/js/load-submission.js")
    assert "statement.value = review.problem_statement || ''" in js, \
        "problem_statement 를 무조건 대입하는 코드가 사라졌다"


def test_language_select_guards_unknown_values(client):
    """DB language 는 자유 문자열이다 — select 에 없는 값을 넣으면 빈 select 가 된다."""
    js = _asset(client, "/static/js/load-submission.js")
    assert "sel.options" in js and "detectLanguage" in js, \
        "select 에 있는 값인지 확인하고 없으면 detectLanguage 로 폴백하는 가드가 사라졌다"


def test_tab_switching_lives_only_in_tabs_js(client):
    """탭 전환 로직은 tabs.js 한 곳에만 둔다.

    다른 모듈이 같은 클래스 토글을 갖고 있으면 탭별 lazy loader 와 모바일 메뉴 닫기를
    건너뛴다.
    """
    tabs = _asset(client, "/static/js/tabs.js")
    assert "function activateTab(" in tabs

    html = client.get("/").text
    others = re.findall(r'src="(/static/js/(?!tabs\.js)[^"]+)"', html)
    assert others, "다른 JS 자산을 찾지 못했다"
    for path in others:
        js = _asset(client, path)
        assert "querySelectorAll('.tab-content')" not in js, \
            f"{path} 가 탭 전환을 자체 구현한다 — activateTab 을 쓰게 고쳐야 한다"
