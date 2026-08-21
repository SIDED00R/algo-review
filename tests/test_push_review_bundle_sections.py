"""push_review_bundle 의 require_sections 계약 (회귀).

수집이 실패했을 때:
- 갱신 경로(require_sections=True, 기본값)는 502 로 막고 GitHub push 를 아예 시도하지 않는다
  — 이미 올라간 문제 설명을 본문 없이 덮어써 지우지 않기 위해서다.
- 아직 문서가 없는 최초 등록 경로(require_sections=False)는 본문 없이도 정상 저장된다.

**두 플랫폼을 모두 돌린다.** 예전에는 CF 만 덮었고, 그 사이 BOJ 의 수집 함수는 실패에도
빈 문자열 dict 를 반환해 `sections` 판정이 BOJ 에서 영원히 거짓이었다 — 가드가 CF 전용인 채로
테스트는 초록이었다. 실패 표현이 None 이든 빈 섹션이든 결과가 같아야 한다.
"""
import pytest
from fastapi import HTTPException

from routes import helpers

_CF_KW = dict(
    platform="codeforces", problem_ref="4A", title="Watermelon",
    tier_name="Codeforces 800", tags=["math"], language="Python 3",
    code="print(1)",
)
_BOJ_KW = dict(
    platform="boj", problem_ref="1000", title="A+B",
    tier_name="Bronze V", tags=["arithmetic"], language="Python 3",
    code="print(1)",
)

# (라벨, push_review_bundle 인자, 수집 함수 이름, 실패 시 그 함수의 반환값, 기대 폴더)
_CASES = [
    ("cf-none", _CF_KW, "get_cf_problem_sections", None, "Codeforces/4A. Watermelon"),
    ("boj-none", _BOJ_KW, "get_boj_problem_sections", None, "백준/Bronze/1000번. A+B"),
    # 수집기가 실패를 빈 섹션으로 표현해도 같은 결과여야 한다.
    ("boj-empty", _BOJ_KW, "get_boj_problem_sections",
     {"description": "", "input": "", "output": ""}, "백준/Bronze/1000번. A+B"),
    ("cf-empty", _CF_KW, "get_cf_problem_sections",
     {"description": "", "input": "", "output": ""}, "Codeforces/4A. Watermelon"),
]
_IDS = [c[0] for c in _CASES]


def _patch(monkeypatch, fetcher, failure_value, readme_exists=True):
    """수집 실패를 주입한다.

    `get_github_file_sha` 도 반드시 패치한다 — 빼먹으면 `_readme_exists()` 가 실제
    api.github.com 으로 나가고(배포 게이트에서 파라미터×매트릭스만큼 외부 호출),
    그 401 예외가 "있다" 로 삼켜져 **틀린 이유로** 초록이 된다. 그러면 가드에서
    `_readme_exists` 호출을 빼버리는 회귀(=최초 등록을 이유 없이 차단)도 통과한다.
    """
    monkeypatch.setattr(helpers.api_client, fetcher, lambda *a, **k: failure_value)
    monkeypatch.setattr(helpers.api_client, "get_github_file_sha",
                        lambda repo, path, token: "sha123" if readme_exists else None)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)
    return calls


@pytest.mark.parametrize("_label,kw,fetcher,failure_value,_folder", _CASES, ids=_IDS)
def test_scrape_failure_blocks_update_path(monkeypatch, _label, kw, fetcher, failure_value, _folder):
    calls = _patch(monkeypatch, fetcher, failure_value)

    with pytest.raises(HTTPException) as exc_info:
        helpers.push_review_bundle("owner/repo", "token", **kw)  # require_sections 기본값 True

    assert exc_info.value.status_code == 502
    assert calls == []  # GitHub push 자체가 시도되면 안 된다


@pytest.mark.parametrize("_label,kw,fetcher,failure_value,folder", _CASES, ids=_IDS)
def test_scrape_failure_allows_first_time_registration(monkeypatch, _label, kw, fetcher,
                                                       failure_value, folder):
    calls = _patch(monkeypatch, fetcher, failure_value, readme_exists=False)

    result = helpers.push_review_bundle("owner/repo", "token", require_sections=False, **kw)

    assert result == folder
    assert len(calls) == 1  # 본문 없이도 push 는 진행된다


@pytest.mark.parametrize("_label,kw,fetcher,_failure,_folder", _CASES, ids=_IDS)
def test_stored_description_skips_scraping(monkeypatch, _label, kw, fetcher, _failure, _folder):
    """호출자가 본문을 주면 수집을 아예 타지 않는다 — 저장된 problem_statement 로 재푸시하는 경로."""
    def _fail(*a, **k):
        pytest.fail(f"{fetcher} 가 호출되면 안 된다 — 호출자가 본문을 넘겼다")

    monkeypatch.setattr(helpers.api_client, fetcher, _fail)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)

    helpers.push_review_bundle("owner/repo", "token", description="【문제】저장된 본문", **kw)

    assert len(calls) == 1
    readme = next(f["content"] for f in calls[0][0][2] if f["path"].endswith("README.md"))
    assert "저장된 본문" in readme


# ── 지킬 문서가 없으면 막지 않는다 (회귀) ──
#
# 가드를 "수집 실패면 무조건 502" 로 두면 최초 등록이 이유 없이 차단된다. acmicpc.net
# 종료로 BOJ 수집이 상시 실패하므로, 실제로 BOJ 의 "GitHub에 올리기"(POST /api/push-review)가
# 전부 502 였고 메시지("잠시 후 다시 시도")는 절대 성공하지 않는 재시도를 유도했다.
# 같은 최초 등록 상황인 pending 경로는 require_sections=False 라 성공하는 비대칭이었다.

def _patch_missing_sections(monkeypatch, fetcher, readme_exists):
    monkeypatch.setattr(helpers.api_client, fetcher, lambda *a, **k: None)
    monkeypatch.setattr(helpers.api_client, "get_github_file_sha",
                        lambda repo, path, token: "sha123" if readme_exists else None)
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append((a, k)) or True)
    return calls


@pytest.mark.parametrize("_label,kw,fetcher,_failure,folder", _CASES, ids=_IDS)
def test_first_time_push_proceeds_when_no_readme_exists(monkeypatch, _label, kw, fetcher,
                                                        _failure, folder):
    calls = _patch_missing_sections(monkeypatch, fetcher, readme_exists=False)

    result = helpers.push_review_bundle("owner/repo", "token", **kw)   # 기본값 True

    assert result == folder
    assert len(calls) == 1, "지킬 문서가 없으면 본문 없이도 push 해야 한다"


@pytest.mark.parametrize("_label,kw,fetcher,_failure,_folder", _CASES, ids=_IDS)
def test_existing_readme_is_still_protected(monkeypatch, _label, kw, fetcher, _failure, _folder):
    calls = _patch_missing_sections(monkeypatch, fetcher, readme_exists=True)

    with pytest.raises(HTTPException) as exc_info:
        helpers.push_review_bundle("owner/repo", "token", **kw)

    assert exc_info.value.status_code == 502
    assert calls == []
    # 메시지가 실행 가능한 안내여야 한다 — "잠시 후 다시 시도" 는 절대 성공하지 않는다.
    assert "붙여 넣" in exc_info.value.detail


@pytest.mark.parametrize("_label,kw,fetcher,_failure,folder", _CASES, ids=_IDS)
def test_readme_check_failure_is_treated_as_existing(monkeypatch, _label, kw, fetcher,
                                                     _failure, folder):
    """확인 자체가 실패하면 '있다'로 본다 — 불확실할 때 덮어쓰면 지켜야 할 문서를 지운다."""
    monkeypatch.setattr(helpers.api_client, fetcher, lambda *a, **k: None)

    def _boom(repo, path, token):
        raise RuntimeError("network")

    monkeypatch.setattr(helpers.api_client, "get_github_file_sha", _boom)
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: pytest.fail("확인 실패 시 push 하면 안 된다"))

    with pytest.raises(HTTPException) as exc_info:
        helpers.push_review_bundle("owner/repo", "token", **kw)
    assert exc_info.value.status_code == 502


@pytest.mark.parametrize("_label,kw,fetcher,_failure,_folder", _CASES, ids=_IDS)
def test_require_sections_false_skips_the_existence_check(monkeypatch, _label, kw, fetcher,
                                                          _failure, _folder):
    """이미 문서가 없음이 확실한 경로는 확인조차 하지 않는다(요청 1회 절약)."""
    monkeypatch.setattr(helpers.api_client, fetcher, lambda *a, **k: None)
    monkeypatch.setattr(helpers.api_client, "get_github_file_sha",
                        lambda repo, path, token: pytest.fail("확인할 필요가 없다"))
    monkeypatch.setattr(helpers.api_client, "push_files_to_github", lambda *a, **k: True)

    helpers.push_review_bundle("owner/repo", "token", require_sections=False, **kw)


# ── 저장된 본문의 세 섹션 구조를 유지한다 (회귀) ──

def test_stored_statement_markers_restore_three_readme_sections(monkeypatch):
    """재푸시는 problem_statement 하나만 갖고 있어서, 쪼개지 않으면 ## 입력·## 출력 이 사라진다.

    백필·스크래핑이 만든 본문은 【문제】/【입력】/【출력】 을 한 덩어리로 묶고 있다.
    """
    stored = "【문제】\n두 정수 A와 B.\n\n【입력】\n첫 줄에 A와 B.\n\n【출력】\nA+B."
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append(a) or True)
    monkeypatch.setattr(helpers.api_client, "get_boj_problem_sections",
                        lambda pid: pytest.fail("본문을 줬으면 수집하면 안 된다"))

    helpers.push_review_bundle("owner/repo", "token", description=stored, **_BOJ_KW)

    readme = next(f["content"] for f in calls[0][2] if f["path"].endswith("README.md"))
    assert "## 문제 설명" in readme and "## 입력" in readme and "## 출력" in readme
    assert "첫 줄에 A와 B." in readme.split("## 입력")[1].split("##")[0]
    assert "【입력】" not in readme, "마커가 그대로 남으면 라벨이 이중으로 보인다"


def test_caller_supplied_sections_are_not_resplit(monkeypatch):
    """호출자가 입력/출력을 직접 주면 그 값을 그대로 쓴다."""
    calls = []
    monkeypatch.setattr(helpers.api_client, "push_files_to_github",
                        lambda *a, **k: calls.append(a) or True)

    helpers.push_review_bundle("owner/repo", "token", description="본문",
                              input_desc="입력부", output_desc="출력부", **_CF_KW)

    readme = next(f["content"] for f in calls[0][2] if f["path"].endswith("README.md"))
    assert "입력부" in readme and "출력부" in readme
