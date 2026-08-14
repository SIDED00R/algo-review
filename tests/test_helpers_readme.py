"""build_readme 의 리뷰 섹션 규약 — 미지정 / 대기 / 완료 세 경우."""
import db
from routes.helpers import build_readme


def _readme(review=None):
    return build_readme("1000", "A+B", "Bronze V", ["구현"], "Python 3",
                        "https://boj.kr/1000", review=review)


def test_readme_without_review_has_no_review_section():
    # 가져오기(import) 경로는 리뷰가 없다 — 섹션 자체가 나오지 않아야 한다.
    assert "## 코드 리뷰" not in _readme()


def test_readme_pending_review_shows_waiting_notice():
    out = _readme({"efficiency": db.PENDING_EFFICIENCY})
    assert "## 코드 리뷰" in out
    assert "AI 리뷰 대기 중" in out


def test_readme_completed_review_includes_details():
    out = _readme({
        "efficiency": "good", "complexity": "O(N)", "better_algorithm": "세그먼트 트리",
        "feedback": "잘 작성된 풀이입니다.", "strengths": ["가독성"], "weaknesses": ["엣지케이스"],
    })
    assert "- 효율성: 효율적" in out
    assert "- 시간복잡도: O(N)" in out
    assert "- 더 나은 알고리즘: 세그먼트 트리" in out
    assert "### 잘한 점" in out and "- 가독성" in out
    assert "### 개선할 점" in out and "- 엣지케이스" in out
    assert "### 상세 피드백" in out and "잘 작성된 풀이입니다." in out
