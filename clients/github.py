import base64
import logging

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
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    try:
        resp = requests.get(url, headers=headers, timeout=10)
        if resp.status_code == 404:
            return None
        resp.raise_for_status()
        return resp.json().get("sha")
    except Exception:
        return None


def push_file_to_github(repo: str, token: str, path: str, content: str, commit_message: str) -> bool:
    headers = {
        "Accept": "application/vnd.github.v3+json",
        "Authorization": f"token {token}",
    }
    url = f"https://api.github.com/repos/{repo}/contents/{path}"
    encoded = base64.b64encode(content.encode("utf-8")).decode("ascii")
    sha = get_github_file_sha(repo, path, token)
    body = {"message": commit_message, "content": encoded}
    if sha:
        body["sha"] = sha
    try:
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


def get_baekjoonhub_problems(repo: str, token: str | None = None) -> list[dict]:
    headers = {"Accept": "application/vnd.github.v3+json"}
    if token:
        headers["Authorization"] = f"token {token}"

    url = f"https://api.github.com/repos/{repo}/git/trees/HEAD?recursive=1"
    resp = requests.get(url, headers=headers, timeout=30)
    resp.raise_for_status()

    tree = resp.json().get("tree", [])
    problems = {}

    BOJ_ROOT_NAMES = {"백준", "boj", "BOJ", "baekjoon", "Baekjoon"}

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

        folder = parts[2]
        try:
            problem_id = int(folder.split(".")[0].strip())
        except ValueError:
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
