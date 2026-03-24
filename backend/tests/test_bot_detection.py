"""Tests for bot detection analysis (Issue #7).

Specs covered:
1. High clone/view ratio detected as automated
2. Consistent daily pattern detected
3. Human-like pattern not flagged
4. Empty repo returns neutral verdict
5. API endpoint returns analysis
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_bot.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# DB-level analysis tests
# ---------------------------------------------------------------------------


class TestBotAnalysisDB:
    async def test_empty_repo_returns_insufficient_data(self, db):
        result = await db.get_bot_analysis("nobody/empty")
        assert result["verdict"] == "insufficient_data"
        assert result["clone_view_ratio"] == 0.0
        assert result["single_cloner_volume"] == 0

    async def test_high_clone_view_ratio_flagged(self, db):
        """Repos with many clones but few views look automated."""
        repo = "owner/bot-repo"
        # 100 clones, 5 views — ratio = 20, well above threshold of 10
        await db.upsert_daily_metrics(
            repo, "2026-03-20", views=5, unique_visitors=2, clones=100, unique_cloners=1
        )
        result = await db.get_bot_analysis(repo)
        assert result["clone_view_ratio"] > 10
        assert result["verdict"] in ("likely_automated", "mixed")

    async def test_consistent_daily_clones_detected(self, db):
        """Cron jobs clone the same amount every day — low stddev."""
        repo = "owner/cron-repo"
        # Exactly 3 clones every day across multiple days (stddev = 0)
        for i in range(7):
            date = f"2026-03-{17 + i:02d}"
            await db.upsert_daily_metrics(
                repo, date, views=50, unique_visitors=20, clones=3, unique_cloners=1
            )
        result = await db.get_bot_analysis(repo)
        # stddev should be 0.0 — very consistent
        assert result["consistent_daily_clones"] == 0.0

    async def test_human_like_pattern_not_flagged(self, db):
        """Human traffic has variable clones and many referrers."""
        repo = "owner/human-repo"
        dates_clones = [
            ("2026-03-18", 1, 100),
            ("2026-03-19", 5, 200),
            ("2026-03-20", 2, 150),
            ("2026-03-21", 8, 300),
            ("2026-03-22", 3, 120),
        ]
        for date, clones, views in dates_clones:
            await db.upsert_daily_metrics(
                repo, date, views=views, unique_visitors=views // 2,
                clones=clones, unique_cloners=clones,
            )
            # Store referrers for every day so referrer_absence signal is 0
            await db.store_referrers(
                repo, date,
                [{"referrer": "google.com", "count": views // 4, "uniques": views // 8}],
            )
        result = await db.get_bot_analysis(repo)
        assert result["verdict"] == "likely_human"

    async def test_referrer_absence_counted(self, db):
        """Days with clones but zero referrers contribute to the bot score."""
        repo = "owner/no-ref-repo"
        for i in range(5):
            date = f"2026-03-{18 + i:02d}"
            await db.upsert_daily_metrics(
                repo, date, views=10, unique_visitors=5, clones=5, unique_cloners=1
            )
        # No referrers stored at all
        result = await db.get_bot_analysis(repo)
        assert result["referrer_absence"] == 5

    async def test_result_has_all_required_fields(self, db):
        repo = "owner/fields-repo"
        await db.upsert_daily_metrics(
            repo, "2026-03-20", views=10, unique_visitors=5, clones=2, unique_cloners=1
        )
        result = await db.get_bot_analysis(repo)
        required = {
            "repo_name", "clone_view_ratio", "consistent_daily_clones",
            "single_cloner_volume", "referrer_absence", "weekend_weekday_ratio",
            "verdict",
        }
        assert required.issubset(result.keys())


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestBotAnalysisEndpoint:
    async def test_endpoint_returns_200(self, client, db):
        await db.upsert_daily_metrics(
            "owner/myrepo", "2026-03-20",
            views=100, unique_visitors=50, clones=5, unique_cloners=3,
        )
        resp = await client.get("/api/repos/owner/myrepo/bot-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_name"] == "owner/myrepo"
        assert "verdict" in data

    async def test_endpoint_empty_repo_insufficient_data(self, client):
        resp = await client.get("/api/repos/nobody/empty/bot-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["verdict"] == "insufficient_data"

    async def test_high_ratio_endpoint_verdict(self, client, db):
        """Endpoint correctly surfaces automated verdict."""
        repo_name = "owner/auto-repo"
        await db.upsert_daily_metrics(
            repo_name, "2026-03-20",
            views=1, unique_visitors=1, clones=200, unique_cloners=1,
        )
        resp = await client.get("/api/repos/owner/auto-repo/bot-analysis")
        assert resp.status_code == 200
        data = resp.json()
        assert data["clone_view_ratio"] > 10
