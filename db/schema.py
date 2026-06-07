from db.connection import get_connection, USE_POSTGRES

# ALTER TABLE 시 허용된 컬럼명만 사용 (f-string SQL injection 방지)
_ALLOWED_REVIEW_COLS = {
    "platform", "problem_ref", "tier_name",
    "complexity", "better_algorithm", "strengths", "weaknesses",
}
_ALLOWED_SOLVED_COLS = {"platform", "problem_ref", "tier_name"}


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    reviews_pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY AUTOINCREMENT"
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS reviews (
            id               {reviews_pk},
            problem_id       INTEGER NOT NULL,
            platform         TEXT NOT NULL DEFAULT 'boj',
            problem_ref      TEXT NOT NULL DEFAULT '',
            title            TEXT NOT NULL,
            tier             INTEGER NOT NULL,
            tier_name        TEXT NOT NULL DEFAULT '',
            tags             TEXT NOT NULL,
            code             TEXT NOT NULL,
            feedback         TEXT NOT NULL,
            efficiency       TEXT NOT NULL,
            complexity       TEXT NOT NULL DEFAULT '',
            better_algorithm TEXT NOT NULL DEFAULT '',
            strengths        TEXT NOT NULL DEFAULT '[]',
            weaknesses       TEXT NOT NULL DEFAULT '[]',
            created_at       TEXT NOT NULL
        )
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS tag_stats (
            tag         TEXT PRIMARY KEY,
            good_count  INTEGER NOT NULL DEFAULT 0,
            poor_count  INTEGER NOT NULL DEFAULT 0,
            total_count INTEGER NOT NULL DEFAULT 0
        )
    """)

    new_columns = [
        ("platform",         "TEXT NOT NULL DEFAULT 'boj'"),
        ("problem_ref",      "TEXT NOT NULL DEFAULT ''"),
        ("tier_name",        "TEXT NOT NULL DEFAULT ''"),
        ("complexity",       "TEXT NOT NULL DEFAULT ''"),
        ("better_algorithm", "TEXT NOT NULL DEFAULT ''"),
        ("strengths",        "TEXT NOT NULL DEFAULT '[]'"),
        ("weaknesses",       "TEXT NOT NULL DEFAULT '[]'"),
    ]
    for col_name, col_def in new_columns:
        if col_name not in _ALLOWED_REVIEW_COLS:
            raise ValueError(f"허용되지 않은 컬럼명: {col_name}")
        try:
            if USE_POSTGRES:
                cur.execute("SAVEPOINT _add_col")
            cur.execute(f"ALTER TABLE reviews ADD COLUMN {col_name} {col_def}")
            if USE_POSTGRES:
                cur.execute("RELEASE SAVEPOINT _add_col")
        except Exception:
            if USE_POSTGRES:
                cur.execute("ROLLBACK TO SAVEPOINT _add_col")

    cur.execute("UPDATE reviews SET platform = 'boj' WHERE platform IS NULL OR platform = ''")
    cur.execute("UPDATE reviews SET problem_ref = CAST(problem_id AS TEXT) WHERE problem_ref IS NULL OR problem_ref = ''")
    cur.execute("UPDATE reviews SET tier_name = '' WHERE tier_name IS NULL")

    cur.execute("""
        CREATE TABLE IF NOT EXISTS solved_history (
            problem_id   INTEGER NOT NULL,
            platform     TEXT NOT NULL DEFAULT 'boj',
            problem_ref  TEXT NOT NULL DEFAULT '',
            title        TEXT NOT NULL,
            tier         INTEGER NOT NULL,
            tier_name    TEXT NOT NULL DEFAULT '',
            tags         TEXT NOT NULL DEFAULT '[]',
            code         TEXT NOT NULL DEFAULT '',
            language     TEXT NOT NULL DEFAULT '',
            imported_at  TEXT NOT NULL,
            PRIMARY KEY (platform, problem_ref)
        )
    """)

    solved_columns = [
        ("platform", "TEXT NOT NULL DEFAULT 'boj'"),
        ("problem_ref", "TEXT NOT NULL DEFAULT ''"),
        ("tier_name", "TEXT NOT NULL DEFAULT ''"),
    ]
    for col_name, col_def in solved_columns:
        if col_name not in _ALLOWED_SOLVED_COLS:
            raise ValueError(f"허용되지 않은 컬럼명: {col_name}")
        try:
            if USE_POSTGRES:
                cur.execute("SAVEPOINT _add_solved_col")
            cur.execute(f"ALTER TABLE solved_history ADD COLUMN {col_name} {col_def}")
            if USE_POSTGRES:
                cur.execute("RELEASE SAVEPOINT _add_solved_col")
        except Exception:
            if USE_POSTGRES:
                cur.execute("ROLLBACK TO SAVEPOINT _add_solved_col")

    cur.execute("UPDATE solved_history SET platform = 'boj' WHERE platform IS NULL OR platform = ''")
    cur.execute("UPDATE solved_history SET problem_ref = CAST(problem_id AS TEXT) WHERE problem_ref IS NULL OR problem_ref = ''")
    cur.execute("UPDATE solved_history SET tier_name = '' WHERE tier_name IS NULL")

    github_pk = "SERIAL PRIMARY KEY" if USE_POSTGRES else "INTEGER PRIMARY KEY"
    cur.execute(f"""
        CREATE TABLE IF NOT EXISTS github_settings (
            id              {github_pk},
            access_token    TEXT NOT NULL DEFAULT '',
            github_username TEXT NOT NULL DEFAULT '',
            target_repo     TEXT NOT NULL DEFAULT '',
            updated_at      TEXT NOT NULL DEFAULT ''
        )
    """)

    # 자주 쓰이는 필터/정렬 컬럼 인덱스 — IF NOT EXISTS로 중복 실행 안전
    for ddl in [
        "CREATE INDEX IF NOT EXISTS idx_reviews_platform        ON reviews (platform)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_platform_ref    ON reviews (platform, problem_ref)",
        "CREATE INDEX IF NOT EXISTS idx_reviews_created_at      ON reviews (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_solved_platform_ref     ON solved_history (platform, problem_ref)",
        "CREATE INDEX IF NOT EXISTS idx_solved_imported_at      ON solved_history (imported_at)",
    ]:
        cur.execute(ddl)

    conn.commit()
    if USE_POSTGRES:
        cur.close()
    conn.close()
