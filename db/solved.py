import json
from datetime import datetime
from db.connection import get_connection, USE_POSTGRES, _ph, _rows_to_dicts


def _normalize_solved_row(row: dict) -> dict:
    from clients.solved_ac import TIER_NAMES

    row["platform"] = (row.get("platform") or "boj").lower()
    row["problem_ref"] = row.get("problem_ref") or str(row.get("problem_id", ""))
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"])
    row["tier_name"] = row.get("tier_name") or TIER_NAMES.get(row.get("tier", 0), "Unrated")
    return row


def save_solved_problem(problem_id: int, title: str, tier: int, tags: list,
                        code: str = "", language: str = "", platform: str = "boj",
                        problem_ref: str | None = None, tier_name: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()
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
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def delete_solved_problem(platform: str, problem_ref: str):
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"DELETE FROM solved_history WHERE platform = {p} AND problem_ref = {p}", (platform, problem_ref))
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def clear_solved_history():
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("DELETE FROM solved_history")
    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def get_cached_problem_info(problem_id: int) -> dict | None:
    from clients.solved_ac import TIER_NAMES
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()

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

    if USE_POSTGRES:
        cur.close()
    conn.close()

    if not row:
        return None

    title, tier, tier_name, tags_json = row[0], row[1], row[2], row[3]
    tags = json.loads(tags_json) if tags_json else []
    return {
        "id": problem_id,
        "title": title,
        "tier": tier,
        "tier_name": tier_name or TIER_NAMES.get(tier, "Unrated"),
        "tags": tags,
    }


def get_solved_problem(platform: str, problem_ref: str) -> dict | None:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"SELECT * FROM solved_history WHERE platform = {p} AND problem_ref = {p}", (platform, problem_ref))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    if not rows:
        return None
    return _normalize_solved_row(rows[0])


def get_solved_history() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT problem_id, platform, problem_ref, title, tier, tier_name, language, imported_at,
               CASE WHEN code != '' THEN 1 ELSE 0 END AS has_code
        FROM solved_history ORDER BY imported_at DESC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        _normalize_solved_row(r)
        r["has_code"] = bool(r["has_code"])
    return rows


def get_solved_cf_refs() -> set:
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    cur.execute(f"SELECT DISTINCT problem_ref FROM reviews WHERE platform = {p}", ("codeforces",))
    refs = {r[0] for r in cur.fetchall()}
    try:
        cur.execute(f"SELECT problem_ref FROM solved_history WHERE platform = {p}", ("codeforces",))
        refs |= {r[0] for r in cur.fetchall()}
    except Exception:
        pass
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return refs


def get_solved_problem_ids() -> set:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT problem_id FROM reviews")
    ids = {r[0] for r in cur.fetchall()}
    try:
        cur.execute("SELECT problem_id FROM solved_history")
        ids |= {r[0] for r in cur.fetchall()}
    except Exception:
        pass
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return ids


def get_solved_problem_keys() -> set[tuple[str, str]]:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT DISTINCT platform, problem_ref FROM reviews")
    keys = {(r[0], str(r[1])) for r in cur.fetchall()}
    try:
        cur.execute("SELECT platform, problem_ref FROM solved_history")
        keys |= {(r[0], str(r[1])) for r in cur.fetchall()}
    except Exception:
        pass
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return keys
