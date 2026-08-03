"""CF 문제 본문 추출 — 수식 구분자 정규화와 수식 이미지 마커 (네트워크 불필요)."""
from lxml import etree

from clients.codeforces import cf_xpath_text, normalize_cf_math


def _parse(html: str):
    return etree.fromstring(html.encode(), etree.HTMLParser())


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


def test_xpath_text_returns_empty_when_no_match():
    tree = _parse("<div><p>nothing</p></div>")
    assert cf_xpath_text(tree, '//div[@id="missing"]') == ""
