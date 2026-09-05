"""ExecuteRequest 의 입력 상한 — ARCHITECTURE.md 가 보안 경계 #6 으로 문서화한 통제.

timeout 은 **거부가 아니라 clamp** 다 — 999 를 보내면 조용히 10 이 된다. 조용한 동작일수록
고정해 두지 않으면 바뀌어도 드러나지 않는다.
"""
import pytest
from pydantic import ValidationError

from routes.models import ExecuteRequest

_BASE = {"code": "print(1)", "language": "Python 3", "stdin": ""}


def test_code_at_the_limit_is_accepted():
    req = ExecuteRequest(**{**_BASE, "code": "x" * 50_000})
    assert len(req.code) == 50_000


def test_code_over_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        ExecuteRequest(**{**_BASE, "code": "x" * 50_001})


def test_stdin_at_the_limit_is_accepted():
    req = ExecuteRequest(**{**_BASE, "stdin": "y" * 10_000})
    assert len(req.stdin) == 10_000


def test_stdin_over_the_limit_is_rejected():
    with pytest.raises(ValidationError):
        ExecuteRequest(**{**_BASE, "stdin": "y" * 10_001})


@pytest.mark.parametrize("given,expected", [
    (1, 1), (5, 5), (10, 10),
    # 범위를 벗어나면 거부가 아니라 clamp 다 — 사용자가 999 를 보내도 10 초로 돈다.
    (0, 1), (-5, 1), (11, 10), (999, 10),
])
def test_timeout_is_clamped_not_rejected(given, expected):
    assert ExecuteRequest(**{**_BASE, "timeout_sec": given}).timeout_sec == expected


def test_empty_code_is_accepted_at_the_model_layer():
    """빈 코드는 모델이 거부하지 않는다 — 현재 동작을 고정한다.

    실행하면 exit 0 + 빈 출력이라 무해하고, 프론트가 먼저 걸러 안내한다
    (problem-modal.js 의 "코드를 먼저 작성해주세요"). 모델에 제약을 추가하려면
    그 프론트 안내와 어느 쪽이 정본인지 먼저 정해야 한다.
    """
    assert ExecuteRequest(**{**_BASE, "code": ""}).code == ""
