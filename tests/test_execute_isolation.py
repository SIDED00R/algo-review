"""코드 실행 격리 (회귀).

ARCHITECTURE.md 는 "subprocess 실행 시 _SAFE_ENV_KEYS 만 허용 → API 키 환경변수 노출 차단"
이라고 적었지만, cwd 를 지정하지 않아 서버의 작업 디렉터리를 상속했다. sys.path[0] 가 리포
루트가 되므로 제출 코드가 `import config` 로 .env 를 읽을 수 있었다(config 의 env_file 은
CWD 상대 경로다). 운영은 .dockerignore + non-root 로 막히지만, 문서의 주장이 실제보다 강했다.
"""
import os

from routes.execute import _BASE_ENV, _run_python


def test_submitted_code_cannot_import_project_modules():
    r = _run_python("import config; print('LEAK')", "", 5)

    assert r["exit_code"] != 0
    assert "LEAK" not in r["stdout"]
    assert "ModuleNotFoundError" in r["stderr"] or "No module named" in r["stderr"]


def test_submitted_code_does_not_run_in_the_repo_directory():
    r = _run_python("import os; print(os.getcwd())", "", 5)

    assert r["exit_code"] == 0
    assert os.path.abspath(r["stdout"].strip()) != os.path.abspath(os.getcwd())


def test_environment_is_filtered_to_safe_keys():
    r = _run_python("import os; print(sorted(os.environ))", "", 5)

    assert r["exit_code"] == 0
    for leaked in ("OPENAI_API_KEY", "DB_PASSWORD", "GITHUB_CLIENT_SECRET",
                   "CODEFORCES_API_SECRET"):
        assert leaked not in r["stdout"]
    assert "OPENAI_API_KEY" not in _BASE_ENV


def test_normal_code_still_runs():
    """격리가 정상 실행을 막지 않아야 한다 — 표준 라이브러리는 쓸 수 있다."""
    r = _run_python("import sys, math, collections\nprint(math.gcd(12, 18), input())",
                    "hello", 5)

    assert r["exit_code"] == 0
    assert r["stdout"].strip() == "6 hello"
