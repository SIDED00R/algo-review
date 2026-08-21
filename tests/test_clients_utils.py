"""언어 문자열 ↔ 확장자 왕복 (회귀).

이 매핑이 저장소 파일명을 정한다. `.txt` 로 떨어지면 _ext_to_language 가 빈 문자열을 돌려주고
rereview 가 "저장된 언어 정보가 없어 파일명을 재현할 수 없습니다"로 재업로드를 거부한다.

예전에 빠져 있던 실제 표기:
- BOJ 채점 목록의 C 계열 표준 연도 표기 (`C99`/`C11`/`C90`, `(Clang)` 변종 포함)
- 컴파일러 이름이 앞에 붙어 `c++` 부분문자열이 없는 C++ 표기 (`GNU G++17 7.3.0`, `Clang++17`)
- `_get_file_extension` 이 만드는데 `_ext_to_language` 가 모르던 확장자 (`.hs`/`.scala`/`.fs`/`.d`)
"""
import pytest

from clients.utils import _ext_to_language, _get_file_extension

# 실제로 관측되는 언어 문자열 → 기대 확장자
_CASES = [
    # BOJ C 계열 — 예전에는 전부 .txt 였다
    ("C99", ".c"), ("C11", ".c"), ("C90", ".c"),
    ("C99 (Clang)", ".c"), ("C11 (Clang)", ".c"), ("C2x", ".c"),
    ("C", ".c"), ("GNU C11", ".c"),
    # C++ — 컴파일러 접두가 붙으면 예전에는 .txt 였다
    ("GNU G++17 7.3.0", ".cpp"), ("GNU G++20 11.2.0 (64 bit, winlibs)", ".cpp"),
    ("Clang++17", ".cpp"), ("C++17", ".cpp"), ("MS C++ 2017", ".cpp"),
    # 나머지
    ("Python 3", ".py"), ("PyPy 3-64", ".py"), ("Java 11", ".java"),
    ("node.js", ".js"), ("Kotlin (JVM)", ".kt"), ("Rust 2018", ".rs"),
    ("Go", ".go"), ("Golang", ".go"), ("Ruby", ".rb"), ("C#", ".cs"),
    ("Swift", ".swift"), ("Haskell", ".hs"), ("Scala", ".scala"),
    ("F#", ".fs"), ("D", ".d"), ("PHP", ".php"), ("TypeScript", ".ts"),
    # 매핑 대상이 아닌 것은 .txt 로 남아야 한다
    ("", ".txt"), ("Text", ".txt"), ("Assembly (32bit)", ".txt"),
]


@pytest.mark.parametrize("language,expected", _CASES, ids=[c[0] or "empty" for c in _CASES])
def test_language_maps_to_expected_extension(language, expected):
    assert _get_file_extension(language) == expected


@pytest.mark.parametrize("language,expected", _CASES, ids=[c[0] or "empty" for c in _CASES])
def test_extension_round_trips_back_to_a_language(language, expected):
    """.txt 가 아닌 모든 확장자는 언어로 되돌아와야 한다 — 한쪽만 알면 재업로드가 거부된다."""
    if expected == ".txt":
        pytest.skip("매핑 대상이 아닌 언어")
    assert _ext_to_language("solution" + expected) != ""


def test_go_is_matched_as_a_word_not_a_substring():
    """`go` 를 부분문자열로 찾으면 이 언어들이 .go 로 걸린다 — BOJ 채점 목록에 실재한다."""
    assert _get_file_extension("Golfscript") != ".go"
    assert _get_file_extension("Algol 68") != ".go"


def test_c_boundary_does_not_swallow_cpp():
    """C 패턴이 C++ 를 먹으면 확장자가 뒤바뀐다."""
    assert _get_file_extension("C++17") == ".cpp"
    assert _get_file_extension("GNU G++17 7.3.0") == ".cpp"


def test_every_produced_extension_is_known_to_the_reverse_map():
    """_get_file_extension 이 만들 수 있는 확장자 전체가 _ext_to_language 에 있어야 한다.

    앞으로 새 언어를 추가할 때 한쪽만 고치는 것을 막는다.
    """
    produced = {_get_file_extension(lang) for lang, _ in _CASES} - {".txt"}
    missing = [ext for ext in sorted(produced) if not _ext_to_language("x" + ext)]
    assert missing == []
