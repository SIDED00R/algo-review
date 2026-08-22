"""소스 파일에 제어 문자가 섞이지 않았는지.

스크립트로 파일을 편집할 때 `\b`·`\n` 같은 이스케이프가 실제 제어 문자로 치환되면
정규식은 조용히 무의미해지고(백스페이스를 요구하는 패턴은 아무것도 매칭하지 않는다),
JS 파일은 문자열이 끊겨 그 파일 전체가 SyntaxError 가 된다. 눈으로는 보이지 않는다.
"""
import pathlib

import pytest

_ROOT = pathlib.Path(__file__).resolve().parent.parent
_EXTS = {".py", ".js", ".css", ".html", ".sh", ".yml", ".md", ".txt", ".toml"}
_SKIP = {"venv", ".git", "__pycache__", ".pytest_cache", "node_modules", "assets"}

# 정상적으로 쓰이는 것: 탭(0x09)·개행(0x0A)·캐리지리턴(0x0D)
_ALLOWED = {0x09, 0x0A, 0x0D}


def _source_files() -> list[pathlib.Path]:
    return [p for p in sorted(_ROOT.rglob("*"))
            if p.is_file() and p.suffix in _EXTS
            and not any(part in _SKIP for part in p.relative_to(_ROOT).parts)]


def test_the_scan_actually_covers_the_repo():
    files = _source_files()
    assert len(files) >= 60, f"{len(files)}개만 훑었다 — 경로·확장자 목록을 확인하라"
    names = {p.name for p in files}
    assert {"utils.js", "reviews.py", "tokens.css", "index.html", "check_js.sh"} <= names


@pytest.mark.parametrize("path", _source_files(), ids=lambda p: p.name)
def test_no_stray_control_characters(path):
    data = path.read_bytes()
    bad = [(i, byte) for i, byte in enumerate(data)
           if byte < 0x20 and byte not in _ALLOWED]
    assert not bad, (
        f"{path.relative_to(_ROOT)} 에 제어 문자 {[(i, hex(b)) for i, b in bad[:5]]} — "
        f"편집 스크립트의 이스케이프가 실제 문자로 치환됐다")
