"""번역 전후 수식 이미지 마커 마스킹 (API 호출 없음)."""
import cf_translator
from cf_translator import _mask_image_markers, _unmask_image_markers

_URL_A = "https://espresso.codeforces.com/a7487d7e62f90136b78ae3fbf0a008396f146e13.png"
_URL_B = "https://espresso.codeforces.com/488158367221f441ba94b9475c03436069df2a7e.png"


def test_mask_replaces_urls_with_indexes():
    masked, urls = _mask_image_markers(f"확률은 ⟦img:{_URL_A}⟧ 이고 상대는 ⟦img:{_URL_B}⟧ 이다")
    assert masked == "확률은 ⟦img:0⟧ 이고 상대는 ⟦img:1⟧ 이다"
    assert urls == [_URL_A, _URL_B]


def test_mask_unmask_round_trip():
    original = f"a ⟦img:{_URL_A}⟧ b ⟦img:{_URL_B}⟧ c"
    masked, urls = _mask_image_markers(original)
    assert _unmask_image_markers(masked, urls) == original


def test_unmask_restores_after_translation_reorders_text():
    # 번역문은 어순이 바뀌지만 마커는 그대로 살아 있다.
    _, urls = _mask_image_markers(f"probability is ⟦img:{_URL_A}⟧ for SmallR")
    translated = "SmallR 의 확률은 ⟦img:0⟧ 이다"
    assert _unmask_image_markers(translated, urls) == f"SmallR 의 확률은 ⟦img:{_URL_A}⟧ 이다"


def test_unmask_drops_index_the_model_made_up():
    _, urls = _mask_image_markers(f"x ⟦img:{_URL_A}⟧")
    assert _unmask_image_markers("있는 것 ⟦img:0⟧ 없는 것 ⟦img:7⟧", urls) == (
        f"있는 것 ⟦img:{_URL_A}⟧ 없는 것 "
    )


def test_mask_leaves_text_without_markers_untouched():
    masked, urls = _mask_image_markers("$n$ 개의 요리")
    assert masked == "$n$ 개의 요리"
    assert urls == []


class _FakeMessage:
    def __init__(self, content):
        self.content = content


class _FakeChoice:
    def __init__(self, content, finish_reason):
        self.message = _FakeMessage(content)
        self.finish_reason = finish_reason


class _FakeCompletions:
    def __init__(self, content, finish_reason):
        self._content = content
        self._finish_reason = finish_reason

    def create(self, **kwargs):
        return type("_FakeResponse", (), {
            "choices": [_FakeChoice(self._content, self._finish_reason)],
        })()


class _FakeOpenAI:
    def __init__(self, content, finish_reason):
        self.chat = type("_FakeChat", (), {
            "completions": _FakeCompletions(content, finish_reason),
        })()


def test_translate_returns_partial_content_when_truncated(monkeypatch):
    # 잘린 응답을 예외로 던지면 routes/problem.py 의 60초 TTL 캐시가 영구히 재시도해
    # 유료 호출이 반복된다 — 잘린 번역이라도 성공으로 간주해 영구 캐시되도록,
    # 예외 대신 부분 번역문 + 안내 문구를 반환해야 한다.
    monkeypatch.setattr(
        cf_translator, "OpenAI",
        lambda **kwargs: _FakeOpenAI("잘린 번역문...", "length"),
    )
    result = cf_translator.translate_cf_text("원문", "제목")
    assert "잘린 번역문..." in result
    assert "일부 생략" in result


def test_translate_returns_content_when_not_truncated(monkeypatch):
    monkeypatch.setattr(
        cf_translator, "OpenAI",
        lambda **kwargs: _FakeOpenAI("완전한 번역문", "stop"),
    )
    assert cf_translator.translate_cf_text("원문", "제목") == "완전한 번역문"
