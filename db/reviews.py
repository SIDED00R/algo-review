import json
from datetime import datetime
from db.connection import get_connection, USE_POSTGRES, _ph, _rows_to_dicts


def _normalize_review_row(row: dict) -> dict:
    from clients.solved_ac import TIER_NAMES

    row["platform"] = (row.get("platform") or "boj").lower()
    row["problem_ref"] = row.get("problem_ref") or str(row.get("problem_id", ""))
    if isinstance(row.get("tags"), str):
        row["tags"] = json.loads(row["tags"])
    if isinstance(row.get("strengths"), str):
        row["strengths"] = json.loads(row.get("strengths") or "[]")
    else:
        row["strengths"] = row.get("strengths", [])
    if isinstance(row.get("weaknesses"), str):
        row["weaknesses"] = json.loads(row.get("weaknesses") or "[]")
    else:
        row["weaknesses"] = row.get("weaknesses", [])
    row["tier_name"] = row.get("tier_name") or TIER_NAMES.get(row.get("tier", 0), "Unrated")
    return row


def save_review(problem_id: int, title: str, tier: int, tags: list,
                code: str, feedback: str, efficiency: str,
                complexity: str = "", better_algorithm: str = "",
                strengths: list = None, weaknesses: list = None,
                platform: str = "boj", problem_ref: str | None = None,
                tier_name: str = ""):
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()

    strengths = strengths or []
    weaknesses = weaknesses or []
    platform = (platform or "boj").strip().lower()
    problem_ref = (problem_ref or str(problem_id)).strip()

    cur.execute(
        f"SELECT COUNT(*) FROM reviews WHERE platform = {p} AND problem_ref = {p}",
        (platform, problem_ref),
    )
    row = cur.fetchone()
    is_first_submission = (row[0] == 0)

    cur.execute(f"""
        INSERT INTO reviews (problem_id, platform, problem_ref, title, tier, tier_name, tags,
                             code, feedback, efficiency, complexity, better_algorithm,
                             strengths, weaknesses, created_at)
        VALUES ({p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p},{p})
    """, (problem_id, platform, problem_ref, title, tier, tier_name,
          json.dumps(tags, ensure_ascii=False), code, feedback, efficiency,
          complexity, better_algorithm or "", json.dumps(strengths, ensure_ascii=False),
          json.dumps(weaknesses, ensure_ascii=False), datetime.now().isoformat()))

    if is_first_submission and platform == "boj":
        for tag in tags:
            if USE_POSTGRES:
                cur.execute(f"""
                    INSERT INTO tag_stats (tag, good_count, poor_count, total_count)
                    VALUES ({p}, 0, 0, 0)
                    ON CONFLICT (tag) DO NOTHING
                """, (tag,))
            else:
                cur.execute(f"""
                    INSERT OR IGNORE INTO tag_stats (tag, good_count, poor_count, total_count)
                    VALUES ({p}, 0, 0, 0)
                """, (tag,))

            if efficiency == "good":
                cur.execute(f"""
                    UPDATE tag_stats
                    SET good_count = good_count + 1, total_count = total_count + 1
                    WHERE tag = {p}
                """, (tag,))
            else:
                cur.execute(f"""
                    UPDATE tag_stats
                    SET poor_count = poor_count + 1, total_count = total_count + 1
                    WHERE tag = {p}
                """, (tag,))

    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()


def get_tag_stats() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("SELECT * FROM tag_stats ORDER BY total_count DESC")
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return rows


def get_total_review_count(platform: str | None = None) -> int:
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    if platform:
        platform = platform.strip().lower()
        cur.execute(
            f"SELECT COUNT(DISTINCT problem_ref) FROM reviews WHERE platform = {p}",
            (platform,),
        )
    else:
        cur.execute("SELECT COUNT(DISTINCT problem_ref) FROM reviews")
    count = cur.fetchone()[0]
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return count


def get_cf_tag_stats() -> list:
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    cur.execute(f"SELECT tags, efficiency FROM reviews WHERE platform = {p}", ("codeforces",))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()

    counts: dict[str, dict] = {}
    for row in rows:
        tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else (row["tags"] or [])
        eff = row.get("efficiency", "poor")
        for tag in tags:
            if tag not in counts:
                counts[tag] = {"tag": tag, "good_count": 0, "poor_count": 0, "total_count": 0}
            counts[tag]["total_count"] += 1
            if eff == "good":
                counts[tag]["good_count"] += 1
            else:
                counts[tag]["poor_count"] += 1

    return sorted(counts.values(), key=lambda x: x["total_count"], reverse=True)


def get_weak_tags(top_n: int = 5) -> list:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT tag, poor_count * 1.0 / total_count AS poor_ratio, total_count
        FROM tag_stats
        WHERE total_count >= 1
        ORDER BY poor_ratio DESC, total_count DESC
        LIMIT {p}
    """, (top_n,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return [r["tag"] for r in rows]


_AVG_TIER_WINDOW = 30  # UI 표시("최근 30개")와 일치


def get_average_tier() -> float:
    """최근 30개 고유 문제의 tier 평균 — 성장에 따라 추천 난이도가 올라간다."""
    conn = get_connection()
    cur = conn.cursor()
    if USE_POSTGRES:
        cur.execute("""
            SELECT tier FROM (
                SELECT DISTINCT ON (platform, problem_ref) tier, created_at
                FROM reviews WHERE tier > 0
                ORDER BY platform, problem_ref, created_at DESC
            ) t ORDER BY created_at DESC LIMIT %s
        """, (_AVG_TIER_WINDOW,))
    else:
        # MAX(created_at) 기준 행의 tier를 정확히 선택 — non-aggregated tier는 GROUP BY에서 보장 안 됨
        cur.execute("""
            SELECT r.tier FROM reviews r
            INNER JOIN (
                SELECT platform, problem_ref, MAX(created_at) AS last_at
                FROM reviews WHERE tier > 0
                GROUP BY platform, problem_ref
            ) latest ON r.platform = latest.platform
                    AND r.problem_ref = latest.problem_ref
                    AND r.created_at = latest.last_at
            WHERE r.tier > 0
            ORDER BY latest.last_at DESC LIMIT ?
        """, (_AVG_TIER_WINDOW,))
    rows = cur.fetchall()
    if USE_POSTGRES:
        cur.close()
    conn.close()

    if not rows:
        return 10.0

    return sum(row[0] for row in rows) / len(rows)


def get_problems_grouped() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT
            problem_id,
            platform,
            problem_ref,
            title,
            tier,
            tier_name,
            tags,
            COUNT(*) AS submission_count,
            MAX(created_at) AS last_submitted,
            STRING_AGG(efficiency, ',' ORDER BY created_at DESC) AS efficiencies
        FROM reviews
        GROUP BY problem_id, platform, problem_ref, title, tier, tier_name, tags
        ORDER BY last_submitted DESC
    """ if USE_POSTGRES else """
        SELECT
            problem_id,
            platform,
            problem_ref,
            title,
            tier,
            tier_name,
            tags,
            COUNT(*) AS submission_count,
            MAX(created_at) AS last_submitted,
            (
                SELECT GROUP_CONCAT(efficiency)
                FROM (
                    SELECT efficiency
                    FROM reviews r2
                    WHERE r2.platform = reviews.platform
                      AND r2.problem_ref = reviews.problem_ref
                    ORDER BY r2.created_at DESC
                )
            ) AS efficiencies
        FROM reviews
        GROUP BY problem_id, platform, problem_ref, title, tier, tier_name, tags
        ORDER BY last_submitted DESC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        _normalize_review_row(r)
    return rows


def get_reviews_by_problem(platform: str, problem_ref: str) -> list:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, problem_id, platform, problem_ref, title, tier, tier_name, tags, code, efficiency, complexity,
               better_algorithm, strengths, weaknesses, feedback, created_at
        FROM reviews WHERE platform = {p} AND problem_ref = {p}
        ORDER BY created_at DESC
    """, (platform, problem_ref))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        _normalize_review_row(r)
    return rows


def get_tier_history() -> list:
    conn = get_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT problem_id, platform, problem_ref, title, tier, tier_name, created_at
        FROM reviews
        WHERE platform = 'boj' AND tier > 0
        ORDER BY created_at ASC
    """)
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    return rows


def get_review_history(limit: int = 10, platform: str | None = None) -> list:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    if platform:
        platform = platform.strip().lower()
        cur.execute(f"""
            SELECT id, problem_id, platform, problem_ref, title, tier, tier_name, tags, efficiency, created_at
            FROM reviews
            WHERE platform = {p}
            ORDER BY created_at DESC
            LIMIT {p}
        """, (platform, limit))
    else:
        cur.execute(f"""
            SELECT id, problem_id, platform, problem_ref, title, tier, tier_name, tags, efficiency, created_at
            FROM reviews ORDER BY created_at DESC LIMIT {p}
        """, (limit,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    for r in rows:
        _normalize_review_row(r)
    return rows


def get_review_detail(review_id: int) -> dict | None:
    p = _ph()
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(f"""
        SELECT id, problem_id, platform, problem_ref, title, tier, tier_name, tags, code,
               feedback, efficiency, complexity, better_algorithm, strengths, weaknesses, created_at
        FROM reviews WHERE id = {p}
    """, (review_id,))
    rows = _rows_to_dicts(cur, cur.fetchall())
    if USE_POSTGRES:
        cur.close()
    conn.close()
    if not rows:
        return None
    return _normalize_review_row(rows[0])


def get_average_cf_rating() -> float:
    conn = get_connection()
    cur = conn.cursor()
    p = _ph()
    if USE_POSTGRES:
        cur.execute(f"""
            SELECT tier_name FROM (
                SELECT DISTINCT ON (problem_ref) tier_name
                FROM reviews WHERE platform = {p}
                ORDER BY problem_ref, created_at DESC
            ) t
        """, ("codeforces",))
    else:
        cur.execute(f"""
            SELECT r.tier_name
            FROM reviews r
            JOIN (
                SELECT problem_ref, MAX(created_at) AS max_created_at
                FROM reviews
                WHERE platform = {p}
                GROUP BY problem_ref
            ) latest
              ON latest.problem_ref = r.problem_ref
             AND latest.max_created_at = r.created_at
            WHERE r.platform = {p}
        """, ("codeforces", "codeforces"))
    rows = cur.fetchall()
    if USE_POSTGRES:
        cur.close()
    conn.close()

    ratings = []
    for row in rows:
        tn = row[0]
        if tn and tn.startswith("Codeforces "):
            try:
                ratings.append(int(tn.split()[-1]))
            except ValueError:
                pass
    return sum(ratings) / len(ratings) if ratings else 1200.0


def get_tag_weakness_data(platform: str | None = None) -> list:
    conn = get_connection()
    cur = conn.cursor()

    if platform:
        p = _ph()
        cur.execute(f"SELECT tags, efficiency, created_at FROM reviews WHERE platform = {p}", (platform,))
        review_rows = _rows_to_dicts(cur, cur.fetchall())
        cur.execute(f"SELECT tags, imported_at FROM solved_history WHERE platform = {p}", (platform,))
        solved_rows = _rows_to_dicts(cur, cur.fetchall())
    else:
        cur.execute("SELECT tags, efficiency, created_at FROM reviews")
        review_rows = _rows_to_dicts(cur, cur.fetchall())
        cur.execute("SELECT tags, imported_at FROM solved_history")
        solved_rows = _rows_to_dicts(cur, cur.fetchall())

    # tag_stats는 BOJ 전용. CF(또는 플랫폼 지정 시)는 reviews에서 직접 poor_ratio 계산.
    if platform and platform != "boj":
        stat_rows = []
    else:
        cur.execute("SELECT tag, poor_count, total_count FROM tag_stats")
        stat_rows = _rows_to_dicts(cur, cur.fetchall())

    if USE_POSTGRES:
        cur.close()
    conn.close()

    tag_data = {}
    for row in review_rows:
        tags = json.loads(row["tags"])
        date = row.get("created_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    for row in solved_rows:
        tags = json.loads(row["tags"])
        date = row.get("imported_at", "")
        for tag in tags:
            if tag not in tag_data:
                tag_data[tag] = {"count": 0, "last_date": ""}
            tag_data[tag]["count"] += 1
            if date > tag_data[tag]["last_date"]:
                tag_data[tag]["last_date"] = date

    poor_map = {}
    if stat_rows:
        # BOJ: tag_stats의 누적 집계 사용
        for s in stat_rows:
            if s["total_count"] > 0:
                poor_map[s["tag"]] = s["poor_count"] / s["total_count"]
    else:
        # 비-BOJ(CF 등): reviews에서 직접 poor_ratio 계산
        tag_eff: dict[str, dict] = {}
        for row in review_rows:
            tags = json.loads(row["tags"]) if isinstance(row["tags"], str) else (row["tags"] or [])
            eff = row.get("efficiency", "poor")
            for tag in tags:
                if tag not in tag_eff:
                    tag_eff[tag] = {"good": 0, "total": 0}
                tag_eff[tag]["total"] += 1
                if eff == "good":
                    tag_eff[tag]["good"] += 1
        for tag, counts in tag_eff.items():
            if counts["total"] > 0:
                poor_map[tag] = 1 - counts["good"] / counts["total"]

    return [
        {
            "tag": tag,
            "solve_count": data["count"],
            "last_solved_at": data["last_date"],
            "poor_ratio": poor_map.get(tag, 0.0),
        }
        for tag, data in tag_data.items()
    ]
