def get_problem_url(platform: str, problem_ref: str | int) -> str:
    from clients.codeforces import normalize_codeforces_problem_ref
    platform = (platform or "boj").lower()
    if platform == "codeforces":
        contest_id, index = normalize_codeforces_problem_ref(str(problem_ref))
        return f"https://codeforces.com/problemset/problem/{contest_id}/{index}"
    return f"https://boj.kr/{problem_ref}"


def _get_file_extension(language: str) -> str:
    lang = (language or "").lower()
    if "c++" in lang or "c plus" in lang:
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
    if "go" in lang:
        return ".go"
    if "ruby" in lang:
        return ".rb"
    if "c#" in lang or "csharp" in lang:
        return ".cs"
    if lang.startswith("c ") or lang == "c" or "gnu c" in lang:
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
    if "d " in lang or lang == "d":
        return ".d"
    return ".txt"


def _ext_to_language(filename: str) -> str:
    ext_map = {
        ".py": "Python 3", ".java": "Java", ".cpp": "C++", ".cc": "C++",
        ".c": "C", ".js": "JavaScript", ".ts": "TypeScript", ".kt": "Kotlin",
        ".rs": "Rust", ".go": "Go", ".rb": "Ruby", ".swift": "Swift",
        ".cs": "C#", ".php": "PHP",
    }
    for ext, lang in ext_map.items():
        if filename.endswith(ext):
            return lang
    return ""
