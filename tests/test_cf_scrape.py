"""CF 문제 본문 추출 — 수식 구분자 정규화와 수식 이미지 마커 (네트워크 불필요)."""
from lxml import etree

from clients.codeforces import cf_xpath_text, normalize_cf_math, tex_markers_to_markdown


def _parse(html: str):
    # 실제 CF 페이지는 <meta charset> 이 있어 인코딩이 자동 감지되지만,
    # 조각 HTML 에는 없으므로 여기서 명시해야 한글이 깨지지 않는다.
    return etree.fromstring(html.encode(), etree.HTMLParser(encoding="utf-8"))


def test_normalize_inline_math():
    assert normalize_cf_math("put $$$n$$$ dishes") == "put $n$ dishes"


def test_normalize_display_math():
    assert normalize_cf_math("$$$$$$\\sum_{i=1}^{n} a_i$$$$$$") == "$$\\sum_{i=1}^{n} a_i$$"


def test_normalize_display_and_inline_mixed():
    text = "합은 $$$$$$x + y$$$$$$ 이고 $$$x$$$ 는 정수다"
    assert normalize_cf_math(text) == "합은 $$x + y$$ 이고 $x$ 는 정수다"


def test_normalize_adjacent_inline_math():
    # 인접한 두 수식이 하나로 합쳐지지 않아야 한다(비탐욕 매칭 확인).
    assert normalize_cf_math("$$$a$$$ and $$$b$$$") == "$a$ and $b$"


def test_normalize_leaves_text_without_math_untouched():
    assert normalize_cf_math("no math here") == "no math here"


def test_xpath_text_normalizes_math():
    tree = _parse('<div id="d"><p>put $$$n$$$ dishes, $$$t_i$$$ minutes</p></div>')
    out = cf_xpath_text(tree, '//div[@id="d"]')
    assert "$$$" not in out
    assert "$n$" in out and "$t_i$" in out


def test_xpath_text_replaces_tex_image_with_marker():
    tree = _parse(
        '<div id="d"><p>probability is '
        '<img class="tex-formula" src="https://espresso.codeforces.com/a7487d.png"/>'
        ' for SmallR</p></div>'
    )
    out = cf_xpath_text(tree, '//div[@id="d"]')
    assert "⟦img:https://espresso.codeforces.com/a7487d.png⟧" in out
    # 이미지 뒤 텍스트(tail)가 유실되면 안 된다.
    assert "for SmallR" in out


def test_xpath_text_keeps_image_marker_at_element_start():
    tree = _parse(
        '<div id="d"><p>'
        '<img class="tex-formula" src="https://espresso.codeforces.com/b1.png"/> is the answer'
        '</p></div>'
    )
    out = cf_xpath_text(tree, '//div[@id="d"]')
    assert "⟦img:https://espresso.codeforces.com/b1.png⟧" in out
    assert "is the answer" in out


def test_xpath_text_skips_image_without_src():
    tree = _parse('<div id="d"><p>a <img class="tex-formula"/> b</p></div>')
    out = cf_xpath_text(tree, '//div[@id="d"]')
    assert "⟦img:" not in out


def test_xpath_text_keeps_order_with_preceding_sibling_and_consecutive_images():
    # img 앞에 엘리먼트 형제가 있으면 마커가 parent.text 가 아니라 prev.tail 로 붙는다.
    # 연속 이미지까지 함께 걸어 순서와 tail 보존을 확인한다.
    tree = _parse(
        '<div id="d"><p>앞 <b>굵게</b>'
        '<img class="tex-formula" src="https://espresso.codeforces.com/1.png"/>사이'
        '<img class="tex-formula" src="https://espresso.codeforces.com/2.png"/>뒤'
        '</p></div>'
    )
    out = cf_xpath_text(tree, '//div[@id="d"]')
    first = out.index("⟦img:https://espresso.codeforces.com/1.png⟧")
    second = out.index("⟦img:https://espresso.codeforces.com/2.png⟧")
    assert out.index("굵게") < first < out.index("사이") < second < out.index("뒤")


def test_xpath_text_returns_empty_when_no_match():
    tree = _parse("<div><p>nothing</p></div>")
    assert cf_xpath_text(tree, '//div[@id="missing"]') == ""


def test_xpath_text_drops_section_title_and_script():
    # note 추출이 cf_xpath_text 를 타면서 새로 적용된 동작 — 프론트가 '노트' 라벨을
    # 따로 붙이므로 본문에 "Note" 가 섞이면 중복이다.
    tree = _parse(
        '<div class="note"><div class="section-title">Note</div>'
        '<script>var mathjax = 1;</script>본문이다</div>'
    )
    out = cf_xpath_text(tree, '//div[contains(@class,"note")]')
    assert out == "본문이다"


def test_tex_span_superscript_becomes_latex():
    # 구형 문제의 범위 표기: 마커를 잃으면 "10  - 6" 처럼 읽혀 의미가 뒤바뀐다.
    tree = _parse(
        '<div id="d"><span class="tex-span">10<sup class="upper-index"> - 6</sup></span></div>'
    )
    assert cf_xpath_text(tree, '//div[@id="d"]') == "$10^{- 6}$"


def test_tex_span_subscript_becomes_latex():
    tree = _parse(
        '<div id="d"><span class="tex-span"><i>t</i><sub class="lower-index">i</sub></span></div>'
    )
    assert cf_xpath_text(tree, '//div[@id="d"]') == "$t_{i}$"


def test_tex_span_wraps_variable_and_normalizes_thin_space():
    # CF 는 수식 안에 얇은 공백(U+2009)을 즐겨 쓴다 — 일반 공백으로 정규화돼야 한다.
    tree = _parse('<div id="d"><span class="tex-span">1 ≤ <i>w</i> ≤ 100</span></div>')
    out = cf_xpath_text(tree, '//div[@id="d"]')
    assert out == "$1 ≤ w ≤ 100$"
    assert " " not in out


def test_tex_span_maps_katex_unsupported_symbol():
    # KaTeX 0.16 은 × 를 유니코드로 인식하지 못한다 (≤ 는 인식하므로 그대로 둔다).
    tree = _parse('<div id="d"><span class="tex-span"><i>n</i> × <i>m</i></span></div>')
    assert cf_xpath_text(tree, '//div[@id="d"]') == "$n \\times m$"


def test_tex_span_with_existing_dollar_is_not_wrapped():
    # 이미 $ 가 있으면 감싸면 짝이 어긋난다.
    tree = _parse('<div id="d"><span class="tex-span">$k$</span></div>')
    assert cf_xpath_text(tree, '//div[@id="d"]') == "$k$"


def test_tex_span_keeps_surrounding_prose():
    tree = _parse(
        '<div id="d"><p>weight <span class="tex-span"><i>w</i></span> kilos</p></div>'
    )
    assert cf_xpath_text(tree, '//div[@id="d"]') == "weight $w$ kilos"


def test_tex_markers_to_markdown():
    text = "확률은 ⟦img:https://espresso.codeforces.com/a.png⟧ 이다"
    assert tex_markers_to_markdown(text) == (
        "확률은 ![수식](https://espresso.codeforces.com/a.png) 이다"
    )


def test_tex_markers_to_markdown_leaves_plain_text_untouched():
    assert tex_markers_to_markdown("마커 없는 본문") == "마커 없는 본문"


def test_multiple_samples_are_all_extracted():
    """CF 는 sample-test 가 문제당 하나이고 그 안에 예제 쌍이 여러 개다. 모든 쌍을 추출한다."""
    from clients.codeforces import _extract_samples

    tree = _parse("""
      <div class="sample-test">
        <div class="input"><pre>1 2</pre></div>
        <div class="output"><pre>3</pre></div>
        <div class="input"><pre>4 5</pre></div>
        <div class="output"><pre>9</pre></div>
      </div>""")
    assert _extract_samples(tree) == [
        {"input": "1 2", "output": "3"},
        {"input": "4 5", "output": "9"},
    ]


def test_sample_without_output_is_preserved():
    """인터랙티브 문제는 output 이 없다 — zip 이면 짧은 쪽에서 잘려 예제가 전부 날아간다."""
    from clients.codeforces import _extract_samples

    tree = _parse("""
      <div class="sample-test">
        <div class="input"><pre>1</pre></div>
        <div class="input"><pre>2</pre></div>
        <div class="output"><pre>ok</pre></div>
      </div>""")
    assert _extract_samples(tree) == [
        {"input": "1", "output": "ok"},
        {"input": "2", "output": ""},
    ]
