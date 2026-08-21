"""프론트의 언어 자동 감지 — 언어별 관용 코드가 올바른 option value 로 판정되는지.

`#code-language` 의 '자동 감지' 와 '지난 제출 불러오기' 가 이 함수의 반환값을 그대로
서버로 보낸다. 잘못 판정하면 저장소에 엉뚱한 확장자로 커밋되고 DB `language` 도 그 값이
된다 — 화면에는 언어가 채워져 있어 사용자가 알아챌 단서가 없다.

파이썬으로 JS 정규식을 재현하지 않는다. 두 엔진의 문법이 달라 통과·실패가 갈린다 —
여기서는 패턴 표를 파싱해 **순서 계약**만 고정하고, 실제 판정은 CDP 실측으로 확인한다.
"""
import re
from pathlib import Path

import pytest

_UTILS = Path(__file__).resolve().parent.parent / "static" / "js" / "utils.js"


@pytest.fixture(scope="module")
def order() -> list[str]:
    src = _UTILS.read_text(encoding="utf-8")
    table = src[src.index("const _LANG_PATTERNS"):src.index("function detectLanguage")]
    return re.findall(r"^\s*\['([^']+)',", table, re.M)


def test_every_dropdown_language_is_reachable_or_deliberately_absent(order):
    """감지 표에 있는 이름은 전부 드롭다운의 option value 여야 한다.

    도메인이 어긋나면 `select.value = <감지값>` 이 조용히 실패해 빈 select 가 된다.
    """
    html = (_UTILS.parent.parent / "index.html").read_text(encoding="utf-8")
    options = set(re.findall(r'<option value="([^"]*)"', html))
    assert set(order) <= options, f"드롭다운에 없는 값: {set(order) - options}"


def test_language_specific_markers_come_before_shared_ones(order):
    """`import`·`print(`·`std::` 같은 공통 마커를 먼저 두면 그 마커를 함께 쓰는 언어를
    전부 흡수한다. Python 은 `import`/`print(`, JavaScript 는 `require(` 를 보므로
    고유 선언 형태를 가진 언어들보다 뒤에 있어야 한다."""
    specific = ["Kotlin", "Rust", "Go", "C#", "Java", "Swift"]
    for name in specific:
        assert name in order, f"{name} 감지가 없다"
        assert order.index(name) < order.index("Python 3"), \
            f"{name} 이 Python 3 보다 뒤에 있어 `import`/`print(` 에 흡수된다"
        assert order.index(name) < order.index("JavaScript"), \
            f"{name} 이 JavaScript 보다 뒤에 있다"


def test_cpp_is_checked_before_c(order):
    """두 언어가 `#include` 를 공유한다. C 를 먼저 보면 모든 C++ 코드가 C 로 떨어진다."""
    assert order.index("GNU C++17") < order.index("C")


def test_c_family_comes_before_python(order):
    r"""`printf(`·`scanf(` 는 `print(` 정규식(`\bprint\s*\(`)에 걸리지 않지만,
    C 계열이 뒤에 있으면 `#include` 만 있는 코드가 다른 분기로 샐 수 있다."""
    assert order.index("C") < order.index("Python 3")
