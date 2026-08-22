r"""프론트의 언어 자동 감지 — 언어별 관용 코드가 올바른 option value 로 판정되는지.

`#code-language` 의 '자동 감지' 와 '지난 제출 불러오기' 가 이 함수의 반환값을 그대로
서버로 보낸다. 잘못 판정하면 저장소에 엉뚱한 확장자로 커밋되고 DB `language` 도 그 값이
된다 — 화면에는 언어가 채워져 있어 사용자가 알아챌 단서가 없고, `_ext_to_language` 가
그 확장자를 다시 같은 언어로 되돌리므로 재리뷰로도 복구되지 않는다.

패턴 표를 파싱해 **파이썬 `re` 로 그대로 돌린다.** 여기 쓰인 문법(`\b \s \w \. [^)] (?!)`)
은 두 엔진의 해석이 같다. 표를 눈으로 읽는 것만으로는 어느 패턴이 어느 언어를 먼저
삼키는지 알 수 없어, 실제 판정을 돌려야 한다.
"""
import re
from pathlib import Path

import pytest

_STATIC = Path(__file__).resolve().parent.parent / "static"
_UTILS = _STATIC / "js" / "utils.js"


def _pattern_table() -> list[tuple[str, re.Pattern]]:
    src = _UTILS.read_text(encoding="utf-8")
    table = src[src.index("const _LANG_PATTERNS"):src.index("function detectLanguage")]
    out = []
    for language, body, flags in re.findall(r"\['([^']+)',\s*/(.*)/([a-z]*)\],\s*$", table, re.M):
        py_flags = re.M if "m" in flags else 0
        out.append((language, re.compile(body, py_flags)))
    return out


@pytest.fixture(scope="module")
def table() -> list[tuple[str, re.Pattern]]:
    parsed = _pattern_table()
    assert len(parsed) >= 8, f"패턴 표를 {len(parsed)}개만 읽었다 — 파서를 확인하라"
    return parsed


def _detect(table, code: str) -> str:
    for language, pattern in table:
        if pattern.search(code):
            return language
    return ""


# 실제 제출에서 관측되는 형태. 언어마다 "그 언어를 쓰면 거의 반드시 나오는" 줄을 고른다.
_SAMPLES = [
    ("Python 3", "import sys\ndef main():\n    print(input())\nmain()"),
    ("Python 3", "fmt = '{}'\nprint(fmt.format(3))"),          # fmt 변수가 Go 로 새면 안 된다
    ("Python 3", "n = int(input())\nprint(n * 2)"),
    ("GNU C++17", "#include <iostream>\nusing namespace std;\nint main(){ int n; cin >> n; cout << n; }"),
    ("GNU C++17", "#include <bits/stdc++.h>\nint main(){ std::vector<int> v; }"),
    ("C", '#include <stdio.h>\nint main(void){ int n; scanf("%d", &n); printf("%d", n); return 0; }'),
    ("Java", "import java.util.Scanner;\npublic class Main { public static void main(String[] a){"
             " Scanner s=new Scanner(System.in); System.out.println(1); } }"),
    ("Java", "import java.util.*;"),                            # 조각만 붙여넣는 경우
    ("Kotlin", "import java.io.*\nfun main() { val n = readLine()!!.toInt(); println(n) }"),
    ("Kotlin", "println(readLine()!!)"),                        # fun main 없는 조각
    ("Swift", "import Foundation\nlet n = Int(readLine()!)!\nprint(n)"),
    ("Rust", "use std::io;\nfn main(){ let mut s = String::new(); }"),
    ("Go", 'package main\nimport "fmt"\nfunc main(){ fmt.Println(1) }'),
    ("C#", "using System;\nclass P { static void Main(){ Console.WriteLine(1); } }"),
    ("JavaScript", "const fs = require('fs');\nconsole.log(1);"),
    ("Ruby", "def solve(n)\n  n * 2\nend\nputs solve(gets.to_i)"),
    ("Ruby", "puts gets.chomp"),
    ("TypeScript", "const lines: string[] = require('fs').readFileSync(0,'utf8').split('\n');\n"
                   "console.log(lines[0]);"),
    ("TypeScript", "interface Point { x: number }\nconst p: Point = { x: 1 };"),
]


@pytest.mark.parametrize("expected,code", _SAMPLES,
                         ids=[f"{i}-{lang}" for i, (lang, _) in enumerate(_SAMPLES)])
def test_idiomatic_code_is_detected_as_its_language(table, expected, code):
    assert _detect(table, code) == expected


def test_unknown_code_returns_empty(table):
    """어느 패턴도 맞지 않으면 '' 를 돌려주고 호출부가 직접 선택을 요구한다."""
    assert _detect(table, "main :: IO ()\nmain = putStrLn \"hi\"") == ""     # Haskell
    assert _detect(table, "") == ""


def test_every_detected_language_is_a_dropdown_option(table):
    """감지 결과가 `#code-language` 의 option value 와 같아야 한다.
    도메인이 어긋나면 `select.value = <감지값>` 이 조용히 실패해 빈 select 가 된다."""
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    options = set(re.findall(r'<option value="([^"]*)"', html))
    detected = {language for language, _ in table}
    assert detected <= options, f"드롭다운에 없는 값: {detected - options}"


def test_dropdown_options_without_a_pattern_are_listed(table):
    """패턴이 없는 옵션은 '자동 감지' 로는 절대 나오지 않는다 — 그 목록을 고정해 둔다.

    여기 없는 옵션이 새로 생기면 이 테스트가 빨강이 나고, 패턴을 넣을지 목록에 넣을지
    결정하게 된다.
    """
    html = (_STATIC / "index.html").read_text(encoding="utf-8")
    lang_select = html[html.index('id="code-language"'):]
    lang_select = lang_select[:lang_select.index("</select>")]
    options = {v for v in re.findall(r'<option value="([^"]*)"', lang_select) if v}
    detected = {language for language, _ in table}
    assert options - detected == {"PyPy3"}, \
        f"패턴 없는 옵션이 바뀌었다: {sorted(options - detected)}"
