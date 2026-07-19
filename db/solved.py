import json
from datetime import datetime
from db.connection import USE_POSTGRES, _ph, _rows_to_dicts, db_cursor
from db.normalize import normalize_common_row, resolve_tier_name


def _normalize_solved_row(row: dict) -> dict:
    return normalize_common_row(row)


def save_solved_problem(problem_id: int, title: str, tier: int, tags: list,
                        code: str = "", language: str = "", platform: str = "boj",
                        problem_ref: str | None = None, tier_name: str = ""):
    p = _ph()
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()
    with db_cursor(commit=True) as cur:
        if USE_POSTGRES:
            cur.execute(f"""
                INSERT INTO solved_history (problem_id, platform, problem_ref, title, tier, tier_name, tags, code, language, imported_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
                ON CONFLICT (platform, problem_ref) DO NOTHING
            """, (problem_id, platform, problem_ref, title, tier, tier_name,
                  json.dumps(tags, ensure_ascii=False), code, language, datetime.now().isoformat()))
        else:
            cur.execute(f"""
                INSERT OR IGNORE INTO solved_history
                    (problem_id, platform, problem_ref, title, tier, tier_name, tags, code, language, imported_at)
                VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
            """, (problem_id, platform, problem_ref, title, tier, tier_name,
                  json.dumps(tags, ensure_ascii=False), code, language, datetime.now().isoformat()))


def delete_solved_problem(platform: str, problem_ref: str):
    p = _ph()
    with db_cursor(commit=True) as cur:
        cur.execute(f"DELETE FROM solved_history WHERE platform = {p} AND problem_ref = {p}", (platform, problem_ref))


def clear_solved_history():
    with db_cursor(commit=True) as cur:
        cur.execute("DELETE FROM solved_history")


def get_cached_problem_info(problem_id: int) -> dict | None:
    p = _ph()
    with db_cursor() as cur:
        cur.execute(f"""
            SELECT title, tier, tier_name, tags
            FROM reviews
            WHERE platform = 'boj' AND problem_id = {p}
            ORDER BY created_at DESC LIMIT 1
        """, (problem_id,))
        row = cur.fetchone()
        if not row:
            cur.execute(f"""
                SELECT title, tier, tier_name, tags
                FROM solved_history
                WHERE platform = 'boj' AND problem_id = {p}
                LIMIT 1
            """, (problem_id,))
            row = cur.fetchone()

    if not row:
        return None

    title, tier, tier_name, tags_json = row[0], row[1], row[2], row[3]
    tags = json.loads(tags_json) if tags_json else []
    return {
        "id": problem_id,
        "title": title,
        "tier": tier,
        "tier_name": resolve_tier_name(tier, tier_name),
        "tags": tags,
    }


def get_solved_problem(platform: str, problem_ref: str) -> dict | None:
    p = _ph()
    with db_cursor() as cur:
        cur.execute(f"SELECT * FROM solved_history WHERE platform = {p} AND problem_ref = {p}", (platform, problem_ref))
        rows = _rows_to_dicts(cur, cur.fetchall())
    if not rows:
        return None
    return _normalize_solved_row(rows[0])


def get_solved_history() -> list:
    with db_cursor() as cur:
        cur.execute("""
            SELECT problem_id, platform, problem_ref, title, tier, tier_name, language, imported_at,
                   CASE WHEN code != '' THEN 1 ELSE 0 END AS has_code
            FROM solved_history ORDER BY imported_at DESC
        """)
        rows = _rows_to_dicts(cur, cur.fetchall())
    for r in rows:
        _normalize_solved_row(r)
        r["has_code"] = bool(r["has_code"])
    return rows


def get_solved_cf_refs() -> set:
    p = _ph()
    with db_cursor() as cur:
        cur.execute(f"SELECT DISTINCT problem_ref FROM reviews WHERE platform = {p}", ("codeforces",))
        refs = {r[0] for r in cur.fetchall()}
        cur.execute(f"SELECT problem_ref FROM solved_history WHERE platform = {p}", ("codeforces",))
        refs |= {r[0] for r in cur.fetchall()}
    return refs


def get_solved_problem_ids() -> set:
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT problem_id FROM reviews")
        ids = {r[0] for r in cur.fetchall()}
        cur.execute("SELECT problem_id FROM solved_history")
        ids |= {r[0] for r in cur.fetchall()}
    return ids


def get_solved_problem_keys() -> set[tuple[str, str]]:
    with db_cursor() as cur:
        cur.execute("SELECT DISTINCT platform, problem_ref FROM reviews")
        keys = {(r[0], str(r[1])) for r in cur.fetchall()}
        cur.execute("SELECT platform, problem_ref FROM solved_history")
        keys |= {(r[0], str(r[1])) for r in cur.fetchall()}
    return keys
