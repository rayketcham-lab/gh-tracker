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

            CREATE TABLE IF NOT EXISTS stargazers (
                repo_name TEXT NOT NULL,
                username TEXT NOT NULL,
                starred_at TEXT,
                UNIQUE(repo_name, username)
            );

            CREATE TABLE IF NOT EXISTS watchers (
                repo_name TEXT NOT NULL,
                username TEXT NOT NULL,
                UNIQUE(repo_name, username)
            );

            CREATE TABLE IF NOT EXISTS forkers (
                repo_name TEXT NOT NULL,
                username TEXT NOT NULL,
                fork_repo TEXT NOT NULL,
                forked_at TEXT,
                UNIQUE(repo_name, username)
            );

            CREATE TABLE IF NOT EXISTS contributors (
                repo_name TEXT NOT NULL,
                username TEXT NOT NULL,
                commits INTEGER DEFAULT 0,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                UNIQUE(repo_name, username)
            );

            CREATE TABLE IF NOT EXISTS issues (
                repo_name TEXT NOT NULL,
                number INTEGER NOT NULL,
                title TEXT NOT NULL,
                state TEXT NOT NULL,
                author TEXT DEFAULT '',
                labels TEXT DEFAULT '',
                created_at TEXT NOT NULL,
                closed_at TEXT,
                is_pr INTEGER DEFAULT 0,
                UNIQUE(repo_name, number)
            );

            CREATE TABLE IF NOT EXISTS repo_metadata (
                repo_name TEXT PRIMARY KEY,
                description TEXT DEFAULT '',
                language TEXT DEFAULT '',
                topics TEXT DEFAULT '',
                stars INTEGER DEFAULT 0,
                forks INTEGER DEFAULT 0,
                watchers_count INTEGER DEFAULT 0,
                open_issues_count INTEGER DEFAULT 0,
                size_kb INTEGER DEFAULT 0,
                license TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                pushed_at TEXT DEFAULT '',
                default_branch TEXT DEFAULT 'main',
                homepage TEXT DEFAULT '',
                total_commits INTEGER DEFAULT 0,
                releases_count INTEGER DEFAULT 0,
                languages_json TEXT DEFAULT '{}',
                collected_at TEXT DEFAULT '',
                health_percentage INTEGER DEFAULT 0,
                scorecard_score REAL DEFAULT -1,
                scorecard_json TEXT DEFAULT '{}',
                dependent_repos_count INTEGER DEFAULT 0,
                source_rank INTEGER DEFAULT 0,
                security_config_json TEXT DEFAULT '{}'
            );

            CREATE TABLE IF NOT EXISTS commit_activity (
                repo_name TEXT NOT NULL,
                week_timestamp INTEGER NOT NULL,
                days TEXT NOT NULL,
                total INTEGER DEFAULT 0,
                UNIQUE(repo_name, week_timestamp)
            );

            CREATE TABLE IF NOT EXISTS code_frequency (
                repo_name TEXT NOT NULL,
                week_timestamp INTEGER NOT NULL,
                additions INTEGER DEFAULT 0,
                deletions INTEGER DEFAULT 0,
                UNIQUE(repo_name, week_timestamp)
            );

            CREATE TABLE IF NOT EXISTS release_assets (
                repo_name TEXT NOT NULL,
                release_tag TEXT NOT NULL,
                asset_name TEXT NOT NULL,
                download_count INTEGER DEFAULT 0,
                size_bytes INTEGER DEFAULT 0,
                created_at TEXT DEFAULT '',
                UNIQUE(repo_name, release_tag, asset_name)
            );

            CREATE TABLE IF NOT EXISTS webhook_events (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                delivery_id TEXT UNIQUE,
                event_type TEXT NOT NULL,
                action TEXT DEFAULT '',
                repo_name TEXT DEFAULT '',
                sender TEXT DEFAULT '',
                payload_json TEXT NOT NULL,
                received_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS watcher_changes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                username TEXT NOT NULL,
                action TEXT NOT NULL,
                detected_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_daily_repo_date ON daily_metrics(repo_name, date);
            CREATE INDEX IF NOT EXISTS idx_issues_repo ON issues(repo_name);
            CREATE INDEX IF NOT EXISTS idx_referrers_repo ON referrers(repo_name, date);
            CREATE INDEX IF NOT EXISTS idx_paths_repo ON popular_paths(repo_name, date);
            CREATE INDEX IF NOT EXISTS idx_stargazers_repo ON stargazers(repo_name);
            CREATE INDEX IF NOT EXISTS idx_watchers_repo ON watchers(repo_name);
            CREATE INDEX IF NOT EXISTS idx_forkers_repo ON forkers(repo_name);
            CREATE INDEX IF NOT EXISTS idx_contributors_repo ON contributors(repo_name);
            CREATE INDEX IF NOT EXISTS idx_metadata_repo ON repo_metadata(repo_name);
            CREATE INDEX IF NOT EXISTS idx_commit_activity_repo ON commit_activity(repo_name);
            CREATE INDEX IF NOT EXISTS idx_code_frequency_repo ON code_frequency(repo_name);
            CREATE INDEX IF NOT EXISTS idx_release_assets_repo ON release_assets(repo_name);
            CREATE INDEX IF NOT EXISTS idx_webhook_events_delivery ON webhook_events(delivery_id);
            CREATE INDEX IF NOT EXISTS idx_webhook_events_received ON webhook_events(received_at);
            CREATE INDEX IF NOT EXISTS idx_watcher_changes_repo ON watcher_changes(repo_name);

            CREATE TABLE IF NOT EXISTS social_mentions (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                platform TEXT NOT NULL,
                url TEXT NOT NULL UNIQUE,
                title TEXT DEFAULT '',
                score INTEGER DEFAULT 0,
                author TEXT DEFAULT '',
                discovered_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS citations (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                repo_name TEXT NOT NULL,
                source TEXT NOT NULL,
                title TEXT DEFAULT '',
                authors TEXT DEFAULT '',
                url TEXT NOT NULL UNIQUE,
                year INTEGER DEFAULT 0,
                citation_count INTEGER DEFAULT 0,
                discovered_at TEXT NOT NULL
            );

            CREATE INDEX IF NOT EXISTS idx_social_mentions_repo ON social_mentions(repo_name);
            CREATE INDEX IF NOT EXISTS idx_citations_repo ON citations(repo_name);

            CREATE TABLE IF NOT EXISTS workflow_runs (
                repo_name TEXT NOT NULL,
                run_id INTEGER NOT NULL,
                workflow_name TEXT DEFAULT '',
                status TEXT DEFAULT '',
                conclusion TEXT DEFAULT '',
                event TEXT DEFAULT '',
                branch TEXT DEFAULT '',
                created_at TEXT DEFAULT '',
                run_started_at TEXT DEFAULT '',
                updated_at TEXT DEFAULT '',
                duration_seconds INTEGER DEFAULT 0,
                UNIQUE(repo_name, run_id)
            );

            CREATE TABLE IF NOT EXISTS punch_card (
                repo_name TEXT NOT NULL,
                day INTEGER NOT NULL,
                hour INTEGER NOT NULL,
                commits INTEGER DEFAULT 0,
                UNIQUE(repo_name, day, hour)
            );

            CREATE TABLE IF NOT EXISTS participation (
                repo_name TEXT NOT NULL,
                week_offset INTEGER NOT NULL,
                all_commits INTEGER DEFAULT 0,
                owner_commits INTEGER DEFAULT 0,
                UNIQUE(repo_name, week_offset)
            );

            CREATE INDEX IF NOT EXISTS idx_workflow_runs_repo ON workflow_runs(repo_name);
            CREATE INDEX IF NOT EXISTS idx_punch_card_repo ON punch_card(repo_name);
            CREATE INDEX IF NOT EXISTS idx_participation_repo ON participation(repo_name);
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

    # --- Visitors ---

    async def get_daily_visitors(
        self, repo_name: str | None = None
    ) -> list[dict]:
        """Get daily visitor data, optionally filtered by repo. Excludes zero-visitor days."""
        if repo_name:
            cursor = await self._db.execute(
                "SELECT repo_name, date, unique_visitors, views "
                "FROM daily_metrics "
                "WHERE repo_name = ? AND unique_visitors > 0 "
                "ORDER BY date DESC",
                (repo_name,),
            )
        else:
            cursor = await self._db.execute(
                "SELECT repo_name, date, unique_visitors, views "
                "FROM daily_metrics "
                "WHERE unique_visitors > 0 "
                "ORDER BY date DESC",
            )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_repo_visitors(self, repo_name: str) -> list[dict]:
        """Get daily visitor breakdown for a repo. Excludes fully-zero days."""
        cursor = await self._db.execute(
            "SELECT date, views, unique_visitors, clones, unique_cloners "
            "FROM daily_metrics "
            "WHERE repo_name = ? AND (views > 0 OR unique_visitors > 0) "
            "ORDER BY date DESC",
            (repo_name,),
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    async def get_visitor_summary(self) -> list[dict]:
        """Get aggregate visitor stats per repo, sorted by total unique visitors."""
        cursor = await self._db.execute(
            "SELECT repo_name, "
            "SUM(unique_visitors) as total_unique_visitors, "
            "SUM(views) as total_views, "
            "SUM(CASE WHEN views > 0 THEN 1 ELSE 0 END) as days_with_traffic "
            "FROM daily_metrics "
            "GROUP BY repo_name "
            "HAVING total_unique_visitors > 0 "
            "ORDER BY total_unique_visitors DESC",
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

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

    # --- People: Stargazers ---

    async def upsert_stargazer(
        self, repo_name: str, username: str, starred_at: str
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO stargazers (repo_name, username, starred_at) "
            "VALUES (?, ?, ?)",
            (repo_name, username, starred_at),
        )
        await self._db.commit()

    async def get_stargazers(self, repo_name: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT username, starred_at FROM stargazers "
            "WHERE repo_name = ? ORDER BY starred_at DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- People: Watchers ---

    async def upsert_watcher(self, repo_name: str, username: str) -> None:
        await self._db.execute(
            "INSERT OR IGNORE INTO watchers (repo_name, username) VALUES (?, ?)",
            (repo_name, username),
        )
        await self._db.commit()

    async def get_watchers(self, repo_name: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT username FROM watchers "
            "WHERE repo_name = ? ORDER BY username",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- People: Forkers ---

    async def upsert_forker(
        self, repo_name: str, username: str, fork_repo: str, forked_at: str
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO forkers "
            "(repo_name, username, fork_repo, forked_at) VALUES (?, ?, ?, ?)",
            (repo_name, username, fork_repo, forked_at),
        )
        await self._db.commit()

    async def get_forkers(self, repo_name: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT username, fork_repo, forked_at FROM forkers "
            "WHERE repo_name = ? ORDER BY forked_at DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- People: Contributors ---

    async def upsert_contributor(
        self, repo_name: str, username: str,
        commits: int = 0, additions: int = 0, deletions: int = 0,
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO contributors "
            "(repo_name, username, commits, additions, deletions) "
            "VALUES (?, ?, ?, ?, ?)",
            (repo_name, username, commits, additions, deletions),
        )
        await self._db.commit()

    async def get_contributors(self, repo_name: str) -> list[dict]:
        cursor = await self._db.execute(
            "SELECT username, commits, additions, deletions FROM contributors "
            "WHERE repo_name = ? ORDER BY commits DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Issues ---

    async def upsert_issue(
        self, repo_name: str, number: int, title: str, state: str,
        author: str, labels: str, created_at: str,
        closed_at: str | None, is_pr: bool = False,
    ) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO issues "
            "(repo_name, number, title, state, author, labels, "
            "created_at, closed_at, is_pr) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_name, number, title, state, author, labels,
             created_at, closed_at, 1 if is_pr else 0),
        )
        await self._db.commit()

    async def get_issues(
        self, repo_name: str,
        state: str | None = None,
        is_pr: bool | None = None,
    ) -> list[dict]:
        sql = "SELECT * FROM issues WHERE repo_name = ?"
        params: list = [repo_name]
        if state:
            sql += " AND state = ?"
            params.append(state)
        if is_pr is not None:
            sql += " AND is_pr = ?"
            params.append(1 if is_pr else 0)
        sql += " ORDER BY created_at DESC"
        cursor = await self._db.execute(sql, params)
        return [dict(row) for row in await cursor.fetchall()]

    async def get_issue_summary(self, repo_name: str) -> dict:
        cursor = await self._db.execute(
            "SELECT "
            "SUM(CASE WHEN state='open' AND is_pr=0 THEN 1 ELSE 0 END) "
            "  as open_issues, "
            "SUM(CASE WHEN state='closed' AND is_pr=0 THEN 1 ELSE 0 END) "
            "  as closed_issues, "
            "SUM(CASE WHEN state='open' AND is_pr=1 THEN 1 ELSE 0 END) "
            "  as open_prs, "
            "SUM(CASE WHEN state='closed' AND is_pr=1 THEN 1 ELSE 0 END) "
            "  as closed_prs, "
            "COUNT(*) as total "
            "FROM issues WHERE repo_name = ?",
            (repo_name,),
        )
        row = await cursor.fetchone()
        if row is None or row["total"] == 0:
            return {
                "open_issues": 0, "closed_issues": 0,
                "open_prs": 0, "closed_prs": 0, "total": 0,
            }
        return dict(row)

    # --- Repo metadata ---

    async def upsert_repo_metadata(self, repo_name: str, **kwargs) -> None:
        """Upsert repo metadata. Accepts any column as a keyword argument."""
        # Always stamp collected_at
        kwargs.setdefault("collected_at", datetime.now(UTC).isoformat())

        # Allowed columns
        allowed = {
            "description", "language", "topics", "stars", "forks",
            "watchers_count", "open_issues_count", "size_kb", "license",
            "created_at", "updated_at", "pushed_at", "default_branch",
            "homepage", "total_commits", "releases_count", "languages_json",
            "collected_at", "health_percentage",
            "scorecard_score", "scorecard_json",
            "dependent_repos_count", "source_rank",
            "security_config_json",
        }
        fields = {k: v for k, v in kwargs.items() if k in allowed}
        fields["repo_name"] = repo_name

        columns = ", ".join(fields.keys())
        placeholders = ", ".join("?" for _ in fields)
        values = list(fields.values())

        await self._db.execute(
            f"INSERT OR REPLACE INTO repo_metadata ({columns}) VALUES ({placeholders})",
            values,
        )
        await self._db.commit()

    async def get_repo_metadata(self, repo_name: str) -> dict | None:
        """Get metadata for a repo."""
        cursor = await self._db.execute(
            "SELECT * FROM repo_metadata WHERE repo_name = ?",
            (repo_name,),
        )
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_all_repo_metadata(self) -> list[dict]:
        """Get metadata for all repos, sorted by stars desc then views."""
        cursor = await self._db.execute(
            "SELECT m.*, COALESCE(v.total_views, 0) AS total_views "
            "FROM repo_metadata m "
            "LEFT JOIN ("
            "  SELECT repo_name, SUM(views) AS total_views "
            "  FROM daily_metrics GROUP BY repo_name"
            ") v ON m.repo_name = v.repo_name "
            "ORDER BY m.stars DESC, total_views DESC"
        )
        rows = await cursor.fetchall()
        return [dict(row) for row in rows]

    # --- Commit activity ---

    async def upsert_commit_activity(
        self, repo_name: str, week_timestamp: int, days: str, total: int
    ) -> None:
        """Upsert a single week of commit activity."""
        await self._db.execute(
            "INSERT OR REPLACE INTO commit_activity "
            "(repo_name, week_timestamp, days, total) VALUES (?, ?, ?, ?)",
            (repo_name, week_timestamp, days, total),
        )
        await self._db.commit()

    async def get_commit_activity(self, repo_name: str) -> list[dict]:
        """Get all 52 weeks of commit activity for a repo."""
        cursor = await self._db.execute(
            "SELECT week_timestamp, days, total FROM commit_activity "
            "WHERE repo_name = ? ORDER BY week_timestamp",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Code frequency ---

    async def upsert_code_frequency(
        self, repo_name: str, week_timestamp: int, additions: int, deletions: int
    ) -> None:
        """Upsert a single week of code frequency (additions/deletions)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO code_frequency "
            "(repo_name, week_timestamp, additions, deletions) VALUES (?, ?, ?, ?)",
            (repo_name, week_timestamp, additions, deletions),
        )
        await self._db.commit()

    async def get_code_frequency(self, repo_name: str) -> list[dict]:
        """Get all weeks of code frequency for a repo."""
        cursor = await self._db.execute(
            "SELECT week_timestamp, additions, deletions FROM code_frequency "
            "WHERE repo_name = ? ORDER BY week_timestamp",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Release assets ---

    async def upsert_release_asset(
        self,
        repo_name: str,
        release_tag: str,
        asset_name: str,
        download_count: int = 0,
        size_bytes: int = 0,
        created_at: str = "",
    ) -> None:
        """Upsert a single release asset with its download count."""
        await self._db.execute(
            "INSERT OR REPLACE INTO release_assets "
            "(repo_name, release_tag, asset_name, download_count, size_bytes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (repo_name, release_tag, asset_name, download_count, size_bytes, created_at),
        )
        await self._db.commit()

    async def get_release_assets(self, repo_name: str) -> list[dict]:
        """Get all release assets for a repo, grouped by release tag."""
        cursor = await self._db.execute(
            "SELECT release_tag, asset_name, download_count, size_bytes, created_at "
            "FROM release_assets WHERE repo_name = ? "
            "ORDER BY created_at DESC, release_tag, asset_name",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Export helpers ---

    async def get_all_daily_metrics(self) -> list[dict]:
        """Return every row in daily_metrics, ordered by repo + date."""
        cursor = await self._db.execute(
            "SELECT * FROM daily_metrics ORDER BY repo_name, date"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_all_stargazers(self) -> list[dict]:
        """Return all stargazers across all repos."""
        cursor = await self._db.execute(
            "SELECT repo_name, username, starred_at FROM stargazers "
            "ORDER BY repo_name, starred_at DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_all_contributors(self) -> list[dict]:
        """Return all contributors across all repos."""
        cursor = await self._db.execute(
            "SELECT repo_name, username, commits, additions, deletions "
            "FROM contributors ORDER BY repo_name, commits DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Social mentions ---

    async def upsert_social_mention(
        self,
        repo_name: str,
        platform: str,
        url: str,
        title: str = "",
        score: int = 0,
        author: str = "",
    ) -> None:
        """Insert or replace a social mention. URL is the unique key."""
        discovered_at = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO social_mentions "
            "(repo_name, platform, url, title, score, author, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (repo_name, platform, url, title, score, author, discovered_at),
        )
        await self._db.commit()

    async def get_social_mentions(self, repo_name: str) -> list[dict]:
        """Get all social mentions for a repo, newest first."""
        cursor = await self._db.execute(
            "SELECT * FROM social_mentions WHERE repo_name = ? "
            "ORDER BY discovered_at DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_recent_social_mentions(self, limit: int = 50) -> list[dict]:
        """Get recent social mentions across all repos."""
        cursor = await self._db.execute(
            "SELECT * FROM social_mentions ORDER BY discovered_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Citations ---

    async def upsert_citation(
        self,
        repo_name: str,
        source: str,
        url: str,
        title: str = "",
        authors: str = "",
        year: int = 0,
        citation_count: int = 0,
    ) -> None:
        """Insert or replace an academic citation. URL is the unique key."""
        discovered_at = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT OR REPLACE INTO citations "
            "(repo_name, source, url, title, authors, year, citation_count, discovered_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_name, source, url, title, authors, year, citation_count, discovered_at),
        )
        await self._db.commit()

    async def get_citations(self, repo_name: str) -> list[dict]:
        """Get all citations for a repo, ordered by citation count desc."""
        cursor = await self._db.execute(
            "SELECT * FROM citations WHERE repo_name = ? "
            "ORDER BY citation_count DESC, year DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def get_citation_summary(self) -> list[dict]:
        """Get citation counts aggregated by repo."""
        cursor = await self._db.execute(
            "SELECT repo_name, "
            "COUNT(*) as total_papers, "
            "SUM(citation_count) as total_citations, "
            "MAX(citation_count) as max_citations "
            "FROM citations "
            "GROUP BY repo_name "
            "ORDER BY total_citations DESC"
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Webhook events ---

    async def store_webhook_event(
        self,
        delivery_id: str,
        event_type: str,
        action: str,
        repo_name: str,
        sender: str,
        payload_json: str,
    ) -> None:
        """Insert a webhook event. Silently ignores duplicate delivery_id."""
        received_at = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT OR IGNORE INTO webhook_events "
            "(delivery_id, event_type, action, repo_name, sender, payload_json, received_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (delivery_id, event_type, action, repo_name, sender, payload_json, received_at),
        )
        await self._db.commit()

    async def get_recent_webhook_events(self, limit: int = 100) -> list[dict]:
        """Return the most recent webhook events, newest first."""
        cursor = await self._db.execute(
            "SELECT id, delivery_id, event_type, action, repo_name, sender, received_at "
            "FROM webhook_events ORDER BY received_at DESC LIMIT ?",
            (limit,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    async def webhook_delivery_exists(self, delivery_id: str) -> bool:
        """Return True if a delivery_id has already been stored."""
        cursor = await self._db.execute(
            "SELECT 1 FROM webhook_events WHERE delivery_id = ?",
            (delivery_id,),
        )
        row = await cursor.fetchone()
        return row is not None

    # --- Bot analysis ---

    async def get_bot_analysis(self, repo_name: str) -> dict:
        """Compute bot/automation indicators from existing traffic data."""
        import math

        cursor = await self._db.execute(
            "SELECT date, views, clones, unique_cloners FROM daily_metrics "
            "WHERE repo_name = ? ORDER BY date",
            (repo_name,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

        if not rows:
            return {
                "repo_name": repo_name,
                "clone_view_ratio": 0.0,
                "consistent_daily_clones": 0.0,
                "single_cloner_volume": 0,
                "referrer_absence": 0,
                "weekend_weekday_ratio": 0.0,
                "verdict": "insufficient_data",
            }

        total_views = sum(r["views"] for r in rows)
        total_clones = sum(r["clones"] for r in rows)

        # clone_view_ratio: high value suggests automated cloning
        clone_view_ratio = total_clones / total_views if total_views > 0 else 0.0

        # consistent_daily_clones: low stddev = cron-like pattern
        clone_counts = [r["clones"] for r in rows]
        if len(clone_counts) > 1:
            mean_clones = sum(clone_counts) / len(clone_counts)
            variance = sum((c - mean_clones) ** 2 for c in clone_counts) / len(clone_counts)
            consistent_daily_clones = math.sqrt(variance)
        else:
            consistent_daily_clones = 0.0

        # single_cloner_volume: max unique_cloners on any single day
        single_cloner_volume = max((r["unique_cloners"] for r in rows), default=0)

        # referrer_absence: days with clones > 0 but no referrers recorded
        referrer_dates_cursor = await self._db.execute(
            "SELECT DISTINCT date FROM referrers WHERE repo_name = ?",
            (repo_name,),
        )
        referrer_dates = {r[0] for r in await referrer_dates_cursor.fetchall()}
        referrer_absence = sum(
            1 for r in rows if r["clones"] > 0 and r["date"] not in referrer_dates
        )

        # weekend_weekday_ratio: bots clone uniformly across all days
        from datetime import date as date_type

        weekend_clones = 0
        weekday_clones = 0
        for r in rows:
            try:
                d = date_type.fromisoformat(r["date"])
                if d.weekday() >= 5:  # Sat=5, Sun=6
                    weekend_clones += r["clones"]
                else:
                    weekday_clones += r["clones"]
            except ValueError:
                pass

        # Normalise by proportion of days (2/7 weekend, 5/7 weekday).
        # Ratio near 1.0 means uniform distribution (bot-like).
        if weekday_clones > 0:
            weekend_weekday_ratio = (weekend_clones / 2) / (weekday_clones / 5)
        elif weekend_clones > 0:
            weekend_weekday_ratio = float("inf")
        else:
            weekend_weekday_ratio = 1.0

        # Tally signals and produce verdict
        bot_signals = 0
        if clone_view_ratio > 10:
            bot_signals += 2
        if consistent_daily_clones < 1.5 and total_clones > 5:
            bot_signals += 1
        if referrer_absence > len(rows) * 0.8 and total_clones > 0:
            bot_signals += 1
        if 0.8 <= weekend_weekday_ratio <= 1.2 and total_clones > 10:
            bot_signals += 1

        if bot_signals >= 3:
            verdict = "likely_automated"
        elif bot_signals == 0:
            verdict = "likely_human"
        else:
            verdict = "mixed"

        return {
            "repo_name": repo_name,
            "clone_view_ratio": round(clone_view_ratio, 4),
            "consistent_daily_clones": round(consistent_daily_clones, 4),
            "single_cloner_volume": single_cloner_volume,
            "referrer_absence": referrer_absence,
            "weekend_weekday_ratio": round(weekend_weekday_ratio, 4),
            "verdict": verdict,
        }

    # --- Watcher changes ---

    async def store_watcher_change(
        self, repo_name: str, username: str, action: str
    ) -> None:
        """Record an 'added' or 'removed' watcher change event."""
        detected_at = datetime.now(UTC).isoformat()
        await self._db.execute(
            "INSERT INTO watcher_changes (repo_name, username, action, detected_at) "
            "VALUES (?, ?, ?, ?)",
            (repo_name, username, action, detected_at),
        )
        await self._db.commit()

    async def get_watcher_changes(self, repo_name: str) -> list[dict]:
        """Return all watcher change records for a repo, newest first."""
        cursor = await self._db.execute(
            "SELECT username, action, detected_at FROM watcher_changes "
            "WHERE repo_name = ? ORDER BY detected_at DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Workflow runs ---

    async def upsert_workflow_run(
        self,
        repo_name: str,
        run_id: int,
        workflow_name: str = "",
        status: str = "",
        conclusion: str = "",
        event: str = "",
        branch: str = "",
        created_at: str = "",
        run_started_at: str = "",
        updated_at: str = "",
        duration_seconds: int = 0,
    ) -> None:
        """Upsert a single CI workflow run."""
        await self._db.execute(
            "INSERT OR REPLACE INTO workflow_runs "
            "(repo_name, run_id, workflow_name, status, conclusion, event, branch, "
            "created_at, run_started_at, updated_at, duration_seconds) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (repo_name, run_id, workflow_name, status, conclusion, event, branch,
             created_at, run_started_at, updated_at, duration_seconds),
        )
        await self._db.commit()

    async def get_workflow_runs(self, repo_name: str) -> list[dict]:
        """Get CI workflow runs for a repo, newest first."""
        cursor = await self._db.execute(
            "SELECT run_id, workflow_name, status, conclusion, event, branch, "
            "created_at, run_started_at, updated_at, duration_seconds "
            "FROM workflow_runs WHERE repo_name = ? ORDER BY created_at DESC",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Punch card ---

    async def upsert_punch_card(
        self, repo_name: str, day: int, hour: int, commits: int
    ) -> None:
        """Upsert a single punch-card entry (day 0-6, hour 0-23)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO punch_card (repo_name, day, hour, commits) "
            "VALUES (?, ?, ?, ?)",
            (repo_name, day, hour, commits),
        )
        await self._db.commit()

    async def get_punch_card(self, repo_name: str) -> list[dict]:
        """Get all 168 punch-card entries for a repo."""
        cursor = await self._db.execute(
            "SELECT day, hour, commits FROM punch_card "
            "WHERE repo_name = ? ORDER BY day, hour",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Participation ---

    async def upsert_participation(
        self,
        repo_name: str,
        week_offset: int,
        all_commits: int,
        owner_commits: int,
    ) -> None:
        """Upsert a participation week (week_offset 0 = oldest, 51 = newest)."""
        await self._db.execute(
            "INSERT OR REPLACE INTO participation "
            "(repo_name, week_offset, all_commits, owner_commits) "
            "VALUES (?, ?, ?, ?)",
            (repo_name, week_offset, all_commits, owner_commits),
        )
        await self._db.commit()

    async def get_participation(self, repo_name: str) -> list[dict]:
        """Get all 52 weeks of participation data for a repo."""
        cursor = await self._db.execute(
            "SELECT week_offset, all_commits, owner_commits FROM participation "
            "WHERE repo_name = ? ORDER BY week_offset",
            (repo_name,),
        )
        return [dict(row) for row in await cursor.fetchall()]

    # --- Referrer trends ---

    async def get_referrer_trends(self, repo_name: str) -> list[dict]:
        """Return referrers grouped by date, annotated with appeared/disappeared sets."""
        cursor = await self._db.execute(
            "SELECT date, referrer, views, unique_visitors "
            "FROM referrers WHERE repo_name = ? ORDER BY date",
            (repo_name,),
        )
        rows = [dict(r) for r in await cursor.fetchall()]

        if not rows:
            return []

        from collections import defaultdict

        by_date: dict = defaultdict(list)
        for row in rows:
            by_date[row["date"]].append(
                {
                    "referrer": row["referrer"],
                    "views": row["views"],
                    "unique_visitors": row["unique_visitors"],
                }
            )

        dates = sorted(by_date.keys())
        result = []
        prev_referrers: set = set()
        for d in dates:
            current_referrers = {e["referrer"] for e in by_date[d]}
            appeared = sorted(current_referrers - prev_referrers)
            disappeared = sorted(prev_referrers - current_referrers)
            result.append(
                {
                    "date": d,
                    "referrers": by_date[d],
                    "appeared": appeared,
                    "disappeared": disappeared,
                }
            )
            prev_referrers = current_referrers

        return result
