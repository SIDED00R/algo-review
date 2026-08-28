r"""LLM 이 준 본문을 dict 로 읽는 경로.

Gemini 호환 엔드포인트는 `response_format={"type":"json_object"}` 를 줘도 문자열 값
안의 이스케이프까지 강제하지 않는다. 모델이 복잡도를 LaTeX 로 적으면 `$O(N \log N)$`
처럼 이스케이프되지 않은 백슬래시가 들어가고, `json.loads` 는 `Invalid \escape` 로 죽는다.
finish_reason 은 `stop` 이라 토큰 초과 가드에도 걸리지 않는다.
"""
import json

import pytest

from analyzer import parse_review_json

_LATEX = r'''{
  "efficiency": "ok",
  "complexity": "시간 복잡도: $O(N^2)$, 공간 복잡도: $O(N)$",
  "better_algorithm": "이분 탐색을 이용한 $O(N \log N)$ 알고리즘 (bisect 모듈 활용)",
  "feedback": "$dp_i$ 를 $i$ 번째 원소로 끝나는 최장 길이로 정의했습니다. $N \le 1000$ 이면 통과합니다.",
  "strengths": ["점화식이 명확함"],
  "weaknesses": ["$N$ 이 커지면 $\Theta(N^2)$ 로 시간 초과"]
}'''


def test_latex_backslashes_are_recovered():
    out = parse_review_json(_LATEX)
    assert out["efficiency"] == "ok"
    assert out["better_algorithm"] == r"이분 탐색을 이용한 $O(N \log N)$ 알고리즘 (bisect 모듈 활용)"
    assert out["weaknesses"] == [r"$N$ 이 커지면 $\Theta(N^2)$ 로 시간 초과"]


@pytest.mark.parametrize("value", [
    r"줄바꿈\n다음 줄",          # \n 은 개행 한 글자
    r"따옴표 \" 안쪽",           # \" 는 따옴표 한 글자
    r"윈도우 경로 C:\\Users",    # \\ 는 백슬래시 한 글자
    r"유니코드 \uAC00 문자",
])
def test_valid_escapes_survive_the_repair(value):
    """복구가 유효한 이스케이프까지 이중화하면 본문이 조용히 망가진다."""
    raw = '{"feedback": "' + value + '"}'
    assert parse_review_json(raw)["feedback"] == json.loads(raw)["feedback"]


def test_valid_escapes_next_to_a_stray_backslash():
    """복구가 도는 본문에서도 유효한 이스케이프는 그대로 해석돼야 한다."""
    raw = r'{"feedback": "C:\\Users 와 \log 와 줄\n뒤"}'
    assert parse_review_json(raw)["feedback"] == "C:\\Users 와 \\log 와 줄\n뒤"


def test_unrepairable_body_raises_the_user_facing_message():
    with pytest.raises(ValueError, match="JSON 으로 해석하지 못했습니다"):
        parse_review_json("```json\n{잘린 응답")
