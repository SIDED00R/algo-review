import re

# BOJ 채점 목록은 표준 연도를 붙여 `C99`·`C11`·`C90`(+ `(Clang)` 변종) 으로 적고, CF 는
# `GNU C11`, 프론트 드롭다운은 `C` 를 쓴다. 세 표기를 한 패턴으로 받는다 — 예전에는
# `startswith("c ")` 만 봐서 BOJ 표기가 전부 .txt 로 떨어졌고, 확장자가 .txt 면
# _ext_to_language 가 빈 문자열을 돌려줘 rereview 가 재업로드를 거부했다.
_C_LANG_RE = re.compile(r"(?:^|\s)c(?:\d+|2x)?(?:\s|$)")
# C++ 은 컴파일러 이름이 앞에 붙어 `c++` 부분문자열이 없는 표기가 많다 — CF 는
# `GNU G++17 7.3.0`, BOJ 는 `Clang++17`. `c++` 만 찾으면 둘 다 .txt 로 떨어진다.
_CPP_LANG_RE = re.compile(r"(?:c|g|clang)\+\+")
# `go` 를 부분문자열로 찾으면 `Algol 68`·`Golfscript` 가 .go 로 걸린다 — 단어로 본다.
_GO_LANG_RE = re.compile(r"(?:^|\s)(?:go|golang)(?:\s|$)")
# `d` 도 같은 이유로 단어 경계가 필요하다 — `"d " in lang` 은 `Standard ML`·`Second Language`
# 를 .d 로 잡는다. BOJ 채점 목록의 실제 표기는 `D`·`D DMD32 v2.101.2` 다.
_D_LANG_RE = re.compile(r"(?:^|\s)d(?:\s|$)")


def get_problem_url(platform: str, problem_ref: str | int) -> str:
    from clients.codeforces import normalize_codeforces_problem_ref
    platform = (platform or "boj").lower()
    if platform == "codeforces":
        contest_id, index = normalize_codeforces_problem_ref(str(problem_ref))
        return f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    return f"https://boj.kr/{problem_ref}"


def _get_file_extension(language: str) -> str:
    lang = (language or "").lower()
    if _CPP_LANG_RE.search(lang) or "c plus" in lang:
        return ".cpp"
    if "python" in lang or "pypy" in lang:
        return ".py"
    if "java" in lang and "javascript" not in lang:
        return ".java"
    if "javascript" in lang or "node" in lang:
        return ".js"
    if "kotlin" in lang:
        return ".kt"
    if "rust" in lang:
        return ".rs"
    if _GO_LANG_RE.search(lang):
        return ".go"
    if "ruby" in lang:
        return ".rb"
    if "c#" in lang or "csharp" in lang:
        return ".cs"
    if _C_LANG_RE.search(lang):
        return ".c"
    if "php" in lang:
        return ".php"
    if "haskell" in lang:
        return ".hs"
    if "scala" in lang:
        return ".scala"
    if "swift" in lang:
        return ".swift"
    if "typescript" in lang:
        return ".ts"
    if "f#" in lang:
        return ".fs"
    if _D_LANG_RE.search(lang):
        return ".d"
    return ".txt"


def _ext_to_language(filename: str) -> str:
    """확장자에서 언어를 되돌린다. _get_file_extension 이 만드는 모든 확장자를 받아야 한다 —
    빠뜨리면 그 언어로 push 한 풀이를 다시 가져올 때 language 가 빈 문자열이 되고,
    rereview 가 파일명을 재현할 수 없다며 재업로드를 거부한다."""
    ext_map = {
        ".py": "Python 3", ".java": "Java", ".cpp": "C++", ".cc": "C++",
        ".c": "C", ".js": "JavaScript", ".ts": "TypeScript", ".kt": "Kotlin",
        ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".swift": "Swift",
        ".cs": "C#", ".php": "PHP", ".hs": "Haskell", ".scala": "Scala",
        ".fs": "F#", ".d": "D",
    }
    for ext, lang in ext_map.items():
        if filename.endswith(ext):
            return lang
    return ""
