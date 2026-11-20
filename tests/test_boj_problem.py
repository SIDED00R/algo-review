"""백준 문제 페이지 추출 — 실제 페이지 구조(2026-11-20 acmicpc.net)를 옮긴 조각으로 본다(네트워크 불필요)."""
from unittest.mock import MagicMock, patch

import pytest

from clients import ProblemNotFound, boj_problem

_PAGE = """<html><body>
<span id="problem_title">오아시스 재결합</span>
<table class="table" id="problem-info"><thead><tr><th style="width:16%;">시간 제한</th>
<th style="width:16%;">메모리 제한</th><th>제출</th><th>정답</th></tr></thead>
<tbody><tr><td>1 초 </td><td>256 MB</td><td>36604</td><td>10440</td></tr></tbody></table>
<div id="problem-body">
<div class="problem-text" id="problem_description">
<p>줄에 서 있는 사람의 키가 주어진다.</p>
<p style="text-align: center;"><img alt="" src="/upload/images/line.png" style="width: 240px;"/></p>
<p>이를 식으로 써보면 F<sub>n</sub> = F<sub>n-1</sub> + F<sub>n-2</sub> 이고 $1 \\le N$ 이다.</p>
</div>
<div class="problem-text" id="problem_input">
<p>첫째 줄에 N이 주어진다. 모든 키는 2<sup>31</sup> 보다 작다. 문자 '<code>#</code>' 는 벽이다.</p>
</div>
<div class="problem-text" id="problem_output">
<p>쌍의 수를 출력한다.</p>
</div>
<div class="problem-text" id="problem_limit">
</div>
<pre class="sampledata" id="sample-input-1">  7
#.#
</pre>
<pre class="sampledata" id="sample-output-1">10
</pre>
<pre class="sampledata" id="sample-input-2">1
</pre>
<div class="problem-text" id="problem_hint">
<p><a href="/help/language">여기</a>를 누르면 예제 소스를 볼 수 있습니다.</p>
</div>
</div>
</body></html>"""


def _response(body: str, status: int = 200) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status
    resp.text = body
    resp.raise_for_status.return_value = None
    return resp


def _scrape(page: str = _PAGE) -> dict:
    with patch.object(boj_problem.requests, "get", lambda *a, **k: _response(page)):
        return boj_problem.scrape_boj_problem(3015)


def test_title_limits_and_url():
    raw = _scrape()
    assert (raw["problem_id"], raw["title"]) == (3015, "오아시스 재결합")
    assert (raw["time_limit"], raw["memory_limit"]) == ("1 초", "256 MB")
    assert raw["url"] == "https://www.acmicpc.net/problem/3015"


def test_section_html_keeps_markup_and_absolutizes_images_and_links():
    html = _scrape()["sections_html"]
    assert "<sub>n-1</sub>" in html["statement"] and "$1 \\le N$" in html["statement"]
    # 앱 도메인에서 그리면 상대 경로가 앱을 가리킨다.
    assert 'src="https://www.acmicpc.net/upload/images/line.png"' in html["statement"]
    assert 'href="https://www.acmicpc.net/help/language"' in html["hint"]
    assert "<code>#</code>" in html["input"]
    # 요소는 있지만 빈 섹션은 빈 문자열이다 — 화면이 빈 카드를 그리지 않는다.
    assert html["limit"] == ""


def test_section_text_folds_scripts_and_keeps_inline_markup_on_one_line():
    text = _scrape()["sections_text"]
    assert text["input"] == "첫째 줄에 N이 주어진다. 모든 키는 2^{31} 보다 작다. 문자 '#' 는 벽이다."
    assert "F_n = F_{n-1} + F_{n-2}" in text["statement"]
    assert text["statement"].splitlines()[0] == "줄에 서 있는 사람의 키가 주어진다."
    assert text["hint"] == "여기를 누르면 예제 소스를 볼 수 있습니다."
    assert text["limit"] == ""


def test_nested_scripts_fold_from_the_inside():
    page = _PAGE.replace("2<sup>31</sup>", "2<sup>2<sup>k</sup></sup>")
    assert "2^{2^k}" in _scrape(page)["sections_text"]["input"]


def test_samples_pair_by_number_and_keep_leading_spaces():
    samples = _scrape()["samples"]
    # 앞 공백은 입력의 일부다. 끝 개행만 지운다. 출력 없는 예제는 빈 출력이다.
    assert samples == [{"input": "  7\n#.#", "output": "10"}, {"input": "1", "output": ""}]


def test_missing_problem_raises_not_found():
    with patch.object(boj_problem.requests, "get", lambda *a, **k: _response("", status=404)):
        with pytest.raises(ProblemNotFound):
            boj_problem.scrape_boj_problem(999999)


def test_page_without_any_section_is_a_failure_not_an_empty_viewer():
    with pytest.raises(RuntimeError):
        _scrape("<html><body><span id='problem_title'>점검 중</span></body></html>")
