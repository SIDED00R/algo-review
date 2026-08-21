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


def test_readme_uses_original_submitted_at_when_given():
    # 재업로드는 원래 제출 시각을 유지해야 앱 기록의 회차 날짜와 어긋나지 않는다.
    # tz 가 없는 값은 UTC 로 간주해 KST(+9)로 변환한다 — db.save_review 가 컨테이너 로컬
    # 시각(Cloud Run 은 UTC)을 tz 없이 저장하므로, 변환하지 않으면 최초 push(KST)와
    # 재푸시(UTC)의 '제출 일자'가 9시간 어긋난다.
    out = build_readme("1000", "A+B", "Bronze V", ["구현"], "Python 3",
                       "https://boj.kr/1000", submitted_at="2026-08-01T09:30:00")
    assert "2026년 8월 1일 18:30:00" in out


def test_readme_converts_tz_aware_submitted_at_to_kst():
    out = build_readme("1000", "A+B", "Bronze V", ["구현"], "Python 3",
                       "https://boj.kr/1000", submitted_at="2026-08-01T09:30:00+00:00")
    assert "2026년 8월 1일 18:30:00" in out


def test_readme_keeps_kst_submitted_at_unchanged():
    out = build_readme("1000", "A+B", "Bronze V", ["구현"], "Python 3",
                       "https://boj.kr/1000", submitted_at="2026-08-01T18:30:00+09:00")
    assert "2026년 8월 1일 18:30:00" in out


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
