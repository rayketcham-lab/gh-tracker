"""SQLite database layer for GitHub metrics persistence."""

from datetime import UTC, datetime

import aiosqlite


class Database:
    def __init__(self, db_path: str) -> None:
        self.db_path = db_path
        self._db: aiosqlite.Connection | None = None

    async def initialize(self) -> None:
        self._db = await aiosqlite.connect(self.db_path)
        self._db.row_factory = aiosqlite.Row
        await self._db.execute("PRAGMA journal_mode=WAL")
        await self._create_tables()

    async def close(self) -> None:
        if self._db:
            await self._db.close()
            self._db = None

    async def _create_tables(self) -> None:
        await self._db.executescript("""
            CREATE TABLE IF NOT EXISTS daily_metrics (
                repo_name TEXT NOT NULL,
                date TEXT NOT NULL,
                views INTEGER DEFAULT 0,
                unique_visitors INTEGER DEFAULT 0,
                clones INTEGER DEFAULT 0,
                unique_cloners INTEGER DEFAULT 0,
                stars_total INTEGER,
                forks_total INTEGER,
                open_issues INTEGER,
                open_prs INTEGER,
                UNIQUE(repo_name, date)
            );

            CREATE TABLE IF NOT EXISTS referrers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                date TEXT NOT NULL,
                referrer TEXT NOT NULL,
                views INTEGER DEFAULT 0,
                unique_visitors INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS popular_paths (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                date TEXT NOT NULL,
                path TEXT NOT NULL,
                title TEXT DEFAULT '',
                views INTEGER DEFAULT 0,
                unique_visitors INTEGER DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS etag_cache (
                endpoint TEXT PRIMARY KEY,
                etag TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS raw_responses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                endpoint TEXT NOT NULL,
                response_body TEXT NOT NULL,
                collected_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_daily_repo_date ON daily_metrics(repo_name, date);
            CREATE INDEX IF NOT EXISTS idx_referrers_repo ON referrers(repo_name, date);
            CREATE INDEX IF NOT EXISTS idx_paths_repo ON popular_paths(repo_name, date);
        """)

    async def list_tables(self) -> list[str]:
        cursor = await self._db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # --- Daily metrics ---

    async def upsert_daily_metrics(
        self,
        repo_name: str,
        date: str,
        views: int | None = None,
        unique_visitors: int | None = None,
        clones: int | None = None,
        unique_cloners: int | None = None,
    ) -> None:
        # Check if row exists
        cursor = await self._db.execute(
            "SELECT * FROM daily_metrics WHERE repo_name = ? AND date = ?",
            (repo_name, date),
        )
        existing = await cursor.fetchone()

        if existing:
            updates = []
            params = []
            if views is not None:
                updates.append("views = ?")
                params.append(views)
            if unique_visitors is not None:
                updates.append("unique_visitors = ?")
                params.append(unique_visitors)
            if clones is not None:
                updates.append("clones = ?")
                params.append(clones)
            if unique_cloners is not None:
                updates.append("unique_cloners = ?")
                params.append(unique_cloners)
            if updates:
                params.extend([repo_name, date])
                await self._db.execute(
                    f"UPDATE daily_metrics SET {', '.join(updates)} "
                    f"WHERE repo_name = ? AND date = ?",
                    params,
                )
        else:
            await self._db.execute(
                "INSERT INTO daily_metrics "
                "(repo_name, date, views, unique_visitors, clones, unique_cloners) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (
                    repo_name, date,
                    views or 0, unique_visitors or 0,
                    clones or 0, unique_cloners or 0,
                ),
            )
        await self._db.commit()

    async def get_daily_metrics(
        self, repo_name: str, start_date: str, end_date: str
    ) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM daily_metrics "
            "WHERE repo_name = ? AND date >= ? AND date <= ? "
            "ORDER BY date",
            (repo_name, start_date, end_date),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def list_repos(self) -> list[str]:
        cursor = await self._db.execute(
            "SELECT DISTINCT repo_name FROM daily_metrics ORDER BY repo_name"
        )
        rows = await cursor.fetchall()
        return [row[0] for row in rows]

    # --- Referrers ---

    async def store_referrers(
        self, repo_name: str, date: str, referrers: list[dict]
    ) -> None:
        # Delete existing referrers for this repo+date to avoid duplicates
        await self._db.execute(
            "DELETE FROM referrers WHERE repo_name = ? AND date = ?",
            (repo_name, date),
        )
        for ref in referrers:
            await self._db.execute(
                "INSERT INTO referrers (repo_name, date, referrer, views, unique_visitors) "
                "VALUES (?, ?, ?, ?, ?)",
                (repo_name, date, ref["referrer"], ref["count"], ref["uniques"]),
            )
        await self._db.commit()

    async def get_referrers(self, repo_name: str, date: str | None = None) -> list[dict]:
        if date:
            cursor = await self._db.execute(
                "SELECT * FROM referrers WHERE repo_name = ? AND date = ? ORDER BY views DESC",
                (repo_name, date),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM referrers WHERE repo_name = ? ORDER BY date DESC, views DESC",
                (repo_name,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Popular paths ---

    async def store_paths(
        self, repo_name: str, date: str, paths: list[dict]
    ) -> None:
        await self._db.execute(
            "DELETE FROM popular_paths WHERE repo_name = ? AND date = ?",
            (repo_name, date),
        )
        for p in paths:
            await self._db.execute(
                "INSERT INTO popular_paths (repo_name, date, path, title, views, unique_visitors) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (repo_name, date, p["path"], p.get("title", ""), p["count"], p["uniques"]),
            )
        await self._db.commit()

    async def get_popular_paths(self, repo_name: str, date: str | None = None) -> list[dict]:
        if date:
            cursor = await self._db.execute(
                "SELECT * FROM popular_paths WHERE repo_name = ? AND date = ? ORDER BY views DESC",
                (repo_name, date),
            )
        else:
            cursor = await self._db.execute(
                "SELECT * FROM popular_paths WHERE repo_name = ? ORDER BY date DESC, views DESC",
                (repo_name,),
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- ETag cache ---

    async def get_etag(self, endpoint: str) -> str | None:
        cursor = await self._db.execute(
            "SELECT etag FROM etag_cache WHERE endpoint = ?", (endpoint,)
        )
        row = await cursor.fetchone()
        return row[0] if row else None

    async def store_etag(self, endpoint: str, etag: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO etag_cache (endpoint, etag) VALUES (?, ?)",
            (endpoint, etag),
        )
        await self._db.commit()

    # --- Raw responses ---

    async def store_raw_response(
        self, repo_name: str, endpoint: str, body: str
    ) -> None:
        now = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT INTO raw_responses (repo_name, endpoint, response_body, collected_at) "
            "VALUES (?, ?, ?, ?)",
            (repo_name, endpoint, body, now),
        )
        await self._db.commit()

    async def get_raw_responses(
        self, repo_name: str, endpoint: str
    ) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT * FROM raw_responses "
            "WHERE repo_name = ? AND endpoint = ? "
            "ORDER BY collected_at DESC",
            (repo_name, endpoint),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]
