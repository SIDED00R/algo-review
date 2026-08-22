r"""소스 파일에 눈에 보이지 않는 문자가 섞이지 않았는지.

스크립트로 파일을 편집하다 이스케이프가 실제 문자로 치환되면 그 결과는 조용하다 —
어느 게이트도 빨강이 되지 않고 눈으로도 보이지 않는다.

- 제어 문자(0x00-0x1F, 0x7F): 정규식이 무의미해진다. `\b` 를 요구하는 패턴에
  실제 백스페이스(0x08)가 들어가면 그 대안은 아무것도 매칭하지 않는다.
- U+00A0(NBSP): 파이썬에서 공백 자리에 들어가면 즉시 SyntaxError.
- U+2028/U+2029: JS 의 줄 종결자다 — 코드 위치가 어긋난다.
- U+200B(ZWSP)·U+FEFF(BOM): 식별자·문자열에 섞이면 비교가 조용히 실패한다.

이 모듈은 **파일 바이트를 직접** 본다. 자기 자신도 검사 대상이므로 raw 문자열로 적는다 —
일반 문자열이면 이 docstring 의 이스케이프가 컴파일 시 실제 제어 문자가 되어, 금지하는
바로 그 문자를 스스로 만든다(파일 바이트에는 없으므로 이 테스트로는 잡히지 않는다).
"""
import pathlib
import unicodedata

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_EXTS = {".py", ".js", ".css", ".html", ".sh", ".yml", ".yaml", ".md", ".txt",
         ".toml", ".ini", ".mako", ".example", ".cfg", ".json"}
# 확장자가 없지만 편집 대상인 파일들(`.env.example` 은 suffix 가 `.example` 이라 _EXTS 로 잡힌다).
_EXTRA_NAMES = {"Dockerfile", ".dockerignore", ".gitattributes"}
_SKIP = {"venv", ".git", "__pycache__", ".pytest_cache", ".ruff_cache",
         "node_modules", "assets"}

# 정상적으로 쓰이는 제어 문자: 탭(0x09)·개행(0x0A)·캐리지리턴(0x0D)
_ALLOWED_CONTROL = {0x09, 0x0A, 0x0D}

# 제어 문자는 아니지만 보이지 않아 같은 사고를 낸다.
_INVISIBLE = {
    0x00A0: "NBSP — 파이썬에서 공백 자리에 오면 SyntaxError",
    0x200B: "ZWSP — 식별자·문자열 비교가 조용히 실패한다",
    0x2028: "LINE SEPARATOR — JS 의 줄 종결자다",
    0x2029: "PARAGRAPH SEPARATOR — JS 의 줄 종결자다",
    0xFEFF: "BOM — 파일 중간에 오면 토큰이 어긋난다",
    # 한글 필러는 category 가 Lo(문자)라 아래 Zs/Cf/Cc 스캔에 걸리지 않는다.
    0x3164: "HANGUL FILLER — 폭이 없는데 문자로 취급된다",
    0x115F: "HANGUL CHOSEONG FILLER — 위와 같다",
    0x1160: "HANGUL JUNGSEONG FILLER — 위와 같다",
}

# 문자 스캔에서 잡을 유니코드 카테고리. Cc 를 넣는 이유는 C1 제어문자(U+0080~U+009F)가
# UTF-8 로 2바이트라 바이트 스캔에 걸리지 않기 때문이다 — 특히 U+0085(NEL)는 파이썬
# str.splitlines() 가 줄바꿈으로 취급한다.
_BAD_CATEGORIES = ("Zs", "Cf", "Cc")

# 의도적으로 담은 예외. 이유를 함께 적는다 — 이유 없이 늘어나면 게이트가 무의미해진다.
_DELIBERATE = {
    # BaekjoonHub 는 폴더명의 공백을 U+2005(FOUR-PER-EM SPACE)로 바꾼다.
    # 그 폴더명을 파싱하는 코드의 픽스처라 실제 문자가 있어야 한다.
    ("tests/test_backfill_statements.py", 0x2005),
    # Codeforces 의 수식 HTML 은 부등호 주위에 U+2009(THIN SPACE)를 넣는다.
    # 그것을 제거하는 코드의 픽스처이자 기대값이라 실제 문자가 있어야 한다.
    ("tests/test_cf_scrape.py", 0x2009),
}


def _source_files() -> list[pathlib.Path]:
    return [p for p in sorted(_ROOT.rglob("*"))
            if p.is_file() and (p.suffix in _EXTS or p.name in _EXTRA_NAMES)
            and not any(part in _SKIP for part in p.relative_to(_ROOT).parts)]


def test_the_scan_actually_covers_the_repo():
    """게이트가 무엇을 훑는지 못박는다 — 경로·확장자가 어긋나면 전부 초록이 된다."""
    files = _source_files()
    assert len(files) >= 100, f"{len(files)}개만 훑었다 — 경로·확장자 목록을 확인하라"
    names = {p.name for p in files}
    assert {"utils.js", "reviews.py", "tokens.css", "index.html", "check_js.sh",
            "Dockerfile", "pyproject.toml", "alembic.ini", ".env.example"} <= names, \
        f"검사 대상에서 빠진 파일이 있다: {names}"


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: str(p.name))
def test_no_stray_or_invisible_characters(path):
    """한 번의 순회로 바이트와 문자를 함께 본다 — 파일마다 두 번 읽지 않는다."""
    rel = path.relative_to(_ROOT).as_posix()
    data = path.read_bytes()
    control = [(i, byte) for i, byte in enumerate(data)
               if (byte < 0x20 and byte not in _ALLOWED_CONTROL) or byte == 0x7F]
    assert not control, (
        f"{rel} 에 제어 문자 {[(i, hex(b)) for i, b in control[:5]]} — "
        f"편집 스크립트의 이스케이프가 실제 문자로 치환됐다")

    try:
        text = data.decode("utf-8")
    except UnicodeDecodeError as exc:
        pytest.fail(f"{rel} 이 UTF-8 이 아니다: {exc}")

    invisible = []
    for index, ch in enumerate(text):
        code = ord(ch)
        if ch == " " or (rel, code) in _DELIBERATE:
            continue
        if code in _INVISIBLE:
            invisible.append((index, code, _INVISIBLE[code]))
        elif code not in _ALLOWED_CONTROL and unicodedata.category(ch) in _BAD_CATEGORIES:
            invisible.append((index, code, unicodedata.name(ch, "?")))
    assert not invisible, (
        f"{rel} 에 보이지 않는 문자: "
        + ", ".join(f"위치 {i} U+{c:04X} ({why})" for i, c, why in invisible[:5]))


def test_the_deliberate_exceptions_still_exist():
    """예외 목록이 낡으면 게이트의 범위가 조용히 넓어진다."""
    for rel, code in _DELIBERATE:
        path = _ROOT / rel
        assert path.is_file(), f"예외 목록의 {rel} 이 없다 — 목록에서 지워라"
        assert chr(code) in path.read_text(encoding="utf-8"), \
            f"{rel} 에 U+{code:04X} 가 더는 없다 — 예외를 지워라"
