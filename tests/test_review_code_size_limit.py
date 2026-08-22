"""저장된 코드를 리뷰하는 경로의 길이 상한.

`/api/review` 는 pydantic 이 요청 본문에서 막지만, 가져오기(`/api/import*`)로 들어온
코드는 그 검증을 거치지 않는다 — 크롤링·API 결과가 그대로 `solved_history` 에 저장된다.
`analyzer.analyze_code` 는 문제 본문만 자르고 **코드는 자르지 않으므로**, 막지 않으면
큰 소스가 그대로 프롬프트가 되어 과금·타임아웃으로 간다.
"""
import pytest
from fastapi import HTTPException

from routes.helpers import require_reviewable_code
from routes.models import MAX_CODE_LENGTH


def test_code_at_the_limit_passes():
    code = "x" * MAX_CODE_LENGTH
    assert require_reviewable_code(code) == code


def test_code_over_the_limit_is_refused():
    with pytest.raises(HTTPException) as caught:
        require_reviewable_code("x" * (MAX_CODE_LENGTH + 1))
    assert caught.value.status_code == 400
    assert "리뷰 탭" in caught.value.detail, "대처법이 없는 메시지다"


@pytest.mark.parametrize("value", ["", None])
def test_missing_code_is_left_to_the_caller(value):
    """빈 코드는 각 라우터가 자기 안내로 막는다 — 여기서 삼키면 메시지가 갈린다."""
    assert require_reviewable_code(value) == value


def test_both_stored_code_review_paths_use_the_guard():
    """가져온 기록 리뷰와 재리뷰 둘 다 이 가드를 거쳐야 한다.

    한쪽만 걸면 다른 쪽으로 같은 코드가 그대로 프롬프트에 들어간다.
    """
    import pathlib
    root = pathlib.Path(__file__).resolve().parent.parent
    for name in ("routes/solved.py", "routes/rereview.py"):
        src = (root / name).read_text(encoding="utf-8")
        assert "require_reviewable_code(" in src, f"{name} 이 상한을 확인하지 않는다"
