import base64
import logging
import re

import requests
from clients.utils import _ext_to_language

logger = logging.getLogger("uvicorn.error")


def exchange_github_code(code: str, client_id: str, client_secret: str) -> str:
    resp = requests.post(
        "https://github.com/login/oauth/access_token",
        json={"client_id": client_id, "client_secret": client_secret, "code": code},
        headers={"Accept": "application/json"},
        timeout=10,
    )
    resp.raise_for_status()
    data = resp.json()
    token = data.get("access_token", "")
    if not token:
        raise ValueError(data.get("error_description") or "GitHub 토큰 발급 실패")
    return token


def get_github_user(token: str) -> dict:
    resp = requests.get(
        "https://api.github.com/user",
        headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def get_github_user_repos(token: str) -> list[dict]:
    repos = []
    for page in range(1, 4):
        resp = requests.get(
            "https://api.github.com/user/repos",
            params={"per_page": 100, "page": page, "sort": "updated", "affiliation": "owner"},
            headers={"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"},
            timeout=10,
        )
        resp.raise_for_status()
        batch = resp.json()
        if not batch:
            break
        repos.extend({"full_name": r["full_name"], "private": r["private"]} for r in batch)
    return repos


def get_github_file_sha(repo: str, path: str, token: str) -> str | None:
    """파일이 없으면(404) None. 그 외 실패(타임아웃 등)는 전파한다 —
    삼키면 호출부가 sha 없이 PUT해 새 파일로 오인, GitHub 422로 이어진다."""
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    resp = requests.get(url, headers=headers, timeout=10)
    if resp.status_code == 404:
        return None
    resp.raise_for_status()
    return resp.json().get("sha")


def push_file_to_github(repo: str, token: str, path: str, content: str, commit_message: str) -> bool:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    try:
        sha = get_github_file_sha(repo, path, token)
        body = {"message": commit_message, "content": encoded}
        if sha:
            body["sha"] = sha
        resp = requests.put(url, json=body, headers=headers, timeout=15)
        resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("GitHub 파일 push 실패 (repo=%s, path=%s): %s", repo, path, e)
        return False


def push_files_to_github(repo: str, token: str, files: list[dict], commit_message: str) -> bool:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    base = f"https://api.github.com/repos/{repo}"
    try:
        ref_resp = requests.get(f"{base}/git/ref/heads/main", headers=headers, timeout=10)
        if ref_resp.status_code == 404:
            ref_resp = requests.get(f"{base}/git/ref/heads/master", headers=headers, timeout=10)
        ref_resp.raise_for_status()
        head_sha = ref_resp.json()["object"]["sha"]

        commit_resp = requests.get(f"{base}/git/commits/{head_sha}", headers=headers, timeout=10)
        commit_resp.raise_for_status()
        base_tree_sha = commit_resp.json()["tree"]["sha"]

        tree_items = [
            {"path": f["path"], "mode": "100644", "type": "blob",
             "content": f["content"]}
            for f in files
        ]
        tree_resp = requests.post(
            f"{base}/git/trees",
            json={"base_tree": base_tree_sha, "tree": tree_items},
            headers=headers, timeout=15,
        )
        tree_resp.raise_for_status()
        new_tree_sha = tree_resp.json()["sha"]

        new_commit_resp = requests.post(
            f"{base}/git/commits",
            json={"message": commit_message, "tree": new_tree_sha, "parents": [head_sha]},
            headers=headers, timeout=15,
        )
        new_commit_resp.raise_for_status()
        new_commit_sha = new_commit_resp.json()["sha"]

        update_resp = requests.patch(
            f"{base}/git/refs/heads/main",
            json={"sha": new_commit_sha},
            headers=headers, timeout=10,
        )
        if update_resp.status_code == 422:
            update_resp = requests.patch(
                f"{base}/git/refs/heads/master",
                json={"sha": new_commit_sha},
                headers=headers, timeout=10,
            )
        update_resp.raise_for_status()
        return True
    except Exception as e:
        logger.warning("GitHub 번들 push 실패 (repo=%s, files=%s): %s",
                       repo, [f["path"] for f in files], e)
        return False


BOJ_ROOT_NAMES = {"백준", "boj", "BOJ", "baekjoon", "Baekjoon"}


def fetch_repo_tree(repo: str, token: str | None = None) -> list[dict]:
    """저장소 전체 트리를 한 번에 받는다(재귀). BaekjoonHub import 와 백필이 공유한다."""
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()
    return resp.json().get("tree", [])


def _leading_problem_number(folder: str) -> int | None:
    """폴더명 앞의 문제 번호를 뗀다. `1000. A＋B` 와 `1000번. A+B` 를 모두 받는다.

    숫자 뒤가 `.` 또는 `번` 이어야 한다 — 그냥 앞자리만 보면 `3142` 가 `31429` 를,
    `1183` 이 `11834` 를 잡는다.
    """
    m = re.match(r"(\d+)(번)?\s*\.", folder.strip())
    return int(m.group(1)) if m else None


def get_boj_readme_paths(repo: str, token: str | None = None) -> dict[int, list[str]]:
    """BOJ 문제 번호 → README.md 경로 후보 목록.

    폴더명을 조립해 맞히려 하면 실패한다 — BaekjoonHub 는 공백을 U+2005 로, 특수문자를
    전각으로 바꾸고 `번` 을 붙이지 않으며, 티어 폴더도 저장 당시 값이라 DB 와 다를 수 있다.
    번호로 트리를 뒤지는 편이 정확하다.

    같은 문제에 폴더가 둘 있을 수 있다(BaekjoonHub 것 + 이 앱이 올린 것). 둘 다 돌려주고
    호출자가 본문이 나오는 것을 고르게 한다.
    """
    paths: dict[int, list[str]] = {}
    for item in fetch_repo_tree(repo, token):
        if item.get("type") != "blob":
            continue
        parts = item["path"].split("/")
        if len(parts) != 4 or parts[0] not in BOJ_ROOT_NAMES or parts[3] != "README.md":
            continue
        problem_id = _leading_problem_number(parts[2])
        if problem_id is None:
            continue
        paths.setdefault(problem_id, []).append(item["path"])
    return paths


def get_baekjoonhub_problems(repo: str, token: str | None = None) -> list[dict]:
    tree = fetch_repo_tree(repo, token)
    problems = {}

    for item in tree:
        if item["type"] != "blob":
            continue
        path = item["path"]
        parts = path.split("/")

        if len(parts) != 4:
            continue
        if parts[0] not in BOJ_ROOT_NAMES:
            continue

        filename = parts[3]
        if filename == "README.md":
            continue

        # BaekjoonHub 는 "1000. A+B", 이 앱이 올린 폴더는 "1000번. 제목" 형태다 — 둘 다 받는다.
        problem_id = _leading_problem_number(parts[2])
        if problem_id is None:
            continue

        if problem_id not in problems:
            problems[problem_id] = {
                "problem_id": problem_id,
                "path": path,
                "language": _ext_to_language(filename),
            }

    return list(problems.values())


def get_raw_github_content(repo: str, path: str, token: str | None = None) -> str:
    url = f"https://raw.githubusercontent.com/{repo}/HEAD/{path}"
    headers = {}
    if token:
        headers["Authorization"] = f"token {token}"
    resp = requests.get(url, headers=headers, timeout=10)
    resp.raise_for_status()
    return resp.text
