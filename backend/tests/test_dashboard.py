"""Tests for GET /api/dashboard cross-repo overview endpoint.

TDD Red phase: all tests should fail before the endpoint is implemented.
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_dashboard.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestDashboardEmpty:
    async def test_dashboard_empty(self, client):
        """No data returns all-zero totals with empty lists."""
        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_repos"] == 0
        assert data["total_views"] == 0
        assert data["total_unique_visitors"] == 0
        assert data["total_clones"] == 0
        assert data["total_stars"] == 0
        assert data["total_forks"] == 0
        assert data["top_referrer"] is None
        assert data["repos"] == []
        assert data["daily_totals"] == []


class TestDashboardSingleRepo:
    async def test_dashboard_single_repo(self, client, db):
        """One repo with traffic data is correctly summarised."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20", views=100, unique_visitors=50, clones=20, unique_cloners=10
        )
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-21", views=100, unique_visitors=50, clones=10, unique_cloners=5
        )
        await db.upsert_stargazer("owner/repo1", "alice", "")
        await db.upsert_stargazer("owner/repo1", "bob", "")
        # A stale row: "carol" has since unstarred. The collector only ever
        # INSERTs, so her row lingers. Counting stargazer rows would report 3.
        await db.upsert_stargazer("owner/repo1", "carol", "")
        await db.upsert_forker("owner/repo1", "charlie", "charlie/repo1", "")
        # GitHub's authoritative counts — this is what the dashboard must use.
        await db.upsert_repo_metadata("owner/repo1", stars=2, forks=1)

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_repos"] == 1
        assert data["total_views"] == 200
        assert data["total_unique_visitors"] == 100
        assert data["total_clones"] == 30
        assert data["total_stars"] == 2
        assert data["total_forks"] == 1

        assert len(data["repos"]) == 1
        repo = data["repos"][0]
        assert repo["repo_name"] == "owner/repo1"
        assert repo["views_30d"] == 200
        assert repo["unique_visitors_30d"] == 100
        assert repo["clones_30d"] == 30
        assert repo["stars"] == 2
        assert repo["forks"] == 1


class TestDashboardMultiRepo:
    async def test_dashboard_multi_repo(self, client, db):
        """Two repos are aggregated correctly into totals."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20",
            views=200, unique_visitors=100, clones=30, unique_cloners=15
        )
        await db.upsert_daily_metrics(
            "owner/repo2", "2026-03-20",
            views=100, unique_visitors=50, clones=20, unique_cloners=10
        )
        await db.upsert_stargazer("owner/repo1", "alice", "")
        await db.upsert_stargazer("owner/repo1", "bob", "")
        await db.upsert_stargazer("owner/repo2", "carol", "")
        await db.upsert_forker("owner/repo1", "dave", "dave/repo1", "")
        await db.upsert_forker("owner/repo1", "eve", "eve/repo1", "")
        await db.upsert_forker("owner/repo2", "frank", "frank/repo2", "")
        # Authoritative counts from GitHub. repo2 reports 1 star even though
        # only one row exists, and repo1 reports 2 — totals must come from here,
        # not from COUNT(*) over the stargazers/forkers tables.
        await db.upsert_repo_metadata("owner/repo1", stars=2, forks=2)
        await db.upsert_repo_metadata("owner/repo2", stars=1, forks=1)

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        assert data["total_repos"] == 2
        assert data["total_views"] == 300
        assert data["total_unique_visitors"] == 150
        assert data["total_clones"] == 50
        assert data["total_stars"] == 3
        assert data["total_forks"] == 3

        repo_names = {r["repo_name"] for r in data["repos"]}
        assert repo_names == {"owner/repo1", "owner/repo2"}


class TestDashboardTopReferrer:
    async def test_dashboard_top_referrer(self, client, db):
        """Top referrer is the one with the most total views across all repos."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20", views=100, unique_visitors=50
        )
        await db.upsert_daily_metrics(
            "owner/repo2", "2026-03-20", views=100, unique_visitors=50
        )

        # google.com has 50+60=110 views; github.com has 40 views
        await db._db.execute(
            "INSERT INTO referrers (repo_name, date, referrer, views, unique_visitors) "
            "VALUES (?, ?, ?, ?, ?)",
            ("owner/repo1", "2026-03-20", "google.com", 50, 25),
        )
        await db._db.execute(
            "INSERT INTO referrers (repo_name, date, referrer, views, unique_visitors) "
            "VALUES (?, ?, ?, ?, ?)",
            ("owner/repo2", "2026-03-20", "google.com", 60, 30),
        )
        await db._db.execute(
            "INSERT INTO referrers (repo_name, date, referrer, views, unique_visitors) "
            "VALUES (?, ?, ?, ?, ?)",
            ("owner/repo1", "2026-03-20", "github.com", 40, 20),
        )
        await db._db.commit()

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_referrer"] == "google.com"

    async def test_dashboard_no_referrers(self, client, db):
        """top_referrer is None when no referrer data exists."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20", views=10, unique_visitors=5
        )
        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert data["top_referrer"] is None


class TestDashboardDailyTotals:
    async def test_dashboard_daily_totals(self, client, db):
        """daily_totals aggregates views and clones across all repos per date."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20", views=100, unique_visitors=50, clones=20, unique_cloners=10
        )
        await db.upsert_daily_metrics(
            "owner/repo2", "2026-03-20", views=50, unique_visitors=25, clones=10, unique_cloners=5
        )
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-21", views=80, unique_visitors=40, clones=15, unique_cloners=8
        )

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        daily = {d["date"]: d for d in data["daily_totals"]}
        assert "2026-03-20" in daily
        assert "2026-03-21" in daily

        assert daily["2026-03-20"]["views"] == 150
        assert daily["2026-03-20"]["clones"] == 30
        assert daily["2026-03-21"]["views"] == 80
        assert daily["2026-03-21"]["clones"] == 15


class TestDashboardTrendCalculation:
    async def test_dashboard_trend_calculation(self, client, db):
        """Trend is % change in views between the most recent 30d and the prior 30d."""
        # Prior 30-day period: data max is 2026-03-10, so current window is
        # 2026-02-09..2026-03-10 and prior window is 2026-01-10..2026-02-08.
        # Put 100 views in prior window and 115 in current window.
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-01-20", views=100, unique_visitors=50
        )
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-10", views=115, unique_visitors=60
        )

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        repo = data["repos"][0]
        assert repo["trend"] is not None
        # 115 views in current 30d, 100 in prior 30d -> +15%
        assert abs(repo["trend"] - 15.0) < 0.1

    async def test_dashboard_no_prior_period(self, client, db):
        """Trend is null when there is no data in the prior 30-day window."""
        await db.upsert_daily_metrics(
            "owner/repo1", "2026-03-20", views=100, unique_visitors=50
        )

        resp = await client.get("/api/dashboard")
        assert resp.status_code == 200
        data = resp.json()

        repo = data["repos"][0]
        # Only one data point, all in current window, nothing in prior window
        assert repo["trend"] is None
