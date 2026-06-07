from datetime import datetime
from db.connection import USE_POSTGRES, _ph, _rows_to_dicts, db_cursor


def get_github_settings() -> dict | None:
    with db_cursor() as cur:
        cur.execute("SELECT access_token, github_username, target_repo FROM github_settings WHERE id = 1")
        rows = _rows_to_dicts(cur, cur.fetchall())
    if not rows:
        return None
    row = rows[0]
    if not row.get("access_token"):
        return None
    return row


def save_github_settings(access_token: str, github_username: str, target_repo: str = ""):
    p = _ph()
    now = datetime.now().isoformat()
    with db_cursor(commit=True) as cur:
        if USE_POSTGRES:
            cur.execute(f"""
                INSERT INTO github_settings (id, access_token, github_username, target_repo, updated_at)
                VALUES (1, {p}, {p}, {p}, {p})
                ON CONFLICT (id) DO UPDATE
                SET access_token = EXCLUDED.access_token,
                    github_username = EXCLUDED.github_username,
                    target_repo = CASE WHEN {p} != '' THEN EXCLUDED.target_repo ELSE github_settings.target_repo END,
                    updated_at = EXCLUDED.updated_at
            """, (access_token, github_username, target_repo, now, target_repo))
        else:
            cur.execute(f"""
                INSERT INTO github_settings (id, access_token, github_username, target_repo, updated_at)
                VALUES (1, {p}, {p}, {p}, {p})
                ON CONFLICT(id) DO UPDATE
                SET access_token = excluded.access_token,
                    github_username = excluded.github_username,
                    target_repo = CASE WHEN {p} != '' THEN excluded.target_repo ELSE github_settings.target_repo END,
                    updated_at = excluded.updated_at
            """, (access_token, github_username, target_repo, now, target_repo))


def update_github_target_repo(target_repo: str):
    p = _ph()
    with db_cursor(commit=True) as cur:
        cur.execute(f"UPDATE github_settings SET target_repo = {p} WHERE id = 1", (target_repo,))


def delete_github_settings():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM github_settings WHERE id = 1")
