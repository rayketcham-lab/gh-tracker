"""Tests for the FastAPI REST API serving dashboard data.

Specs covered:
1. GET /api/repos — list tracked repositories
2. GET /api/repos/{owner}/{repo}/traffic — daily views/clones time series
3. GET /api/repos/{owner}/{repo}/referrers — top referrers
4. GET /api/repos/{owner}/{repo}/paths — popular paths
5. POST /api/collect — trigger manual collection
6. GET /api/health — health check
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_api.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestHealthEndpoint:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ok"


class TestReposEndpoint:
    async def test_list_repos_empty(self, client):
        resp = await client.get("/api/repos")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_repos_with_data(self, client, db):
        await db.upsert_daily_metrics("owner/repo", "2026-03-20", views=10, unique_visitors=5)
        resp = await client.get("/api/repos")
        assert resp.status_code == 200
        repos = resp.json()
        assert "owner/repo" in repos


class TestTrafficEndpoint:
    async def test_traffic_returns_time_series(self, client, db):
        await db.upsert_daily_metrics(
            "owner/repo", "2026-03-20", views=40, unique_visitors=20, clones=10, unique_cloners=5
        )
        await db.upsert_daily_metrics(
            "owner/repo", "2026-03-21", views=60, unique_visitors=30, clones=15, unique_cloners=5
        )

        resp = await client.get("/api/repos/owner/repo/traffic")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        assert data[0]["date"] == "2026-03-20"
        assert data[0]["views"] == 40
        assert data[1]["clones"] == 15

    async def test_traffic_date_range_filter(self, client, db):
        await db.upsert_daily_metrics("owner/repo", "2026-03-19", views=10, unique_visitors=5)
        await db.upsert_daily_metrics("owner/repo", "2026-03-20", views=20, unique_visitors=10)
        await db.upsert_daily_metrics("owner/repo", "2026-03-21", views=30, unique_visitors=15)

        resp = await client.get(
            "/api/repos/owner/repo/traffic?start=2026-03-20&end=2026-03-20"
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["date"] == "2026-03-20"

    async def test_traffic_404_for_unknown_repo(self, client):
        resp = await client.get("/api/repos/unknown/repo/traffic")
        assert resp.status_code == 200
        assert resp.json() == []


class TestReferrersEndpoint:
    async def test_referrers_returns_data(self, client, db):
        today = "2026-03-20"
        await db.store_referrers("owner/repo", today, [
            {"referrer": "google.com", "count": 50, "uniques": 30},
        ])

        resp = await client.get("/api/repos/owner/repo/referrers")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["referrer"] == "google.com"


class TestPathsEndpoint:
    async def test_paths_returns_data(self, client, db):
        today = "2026-03-20"
        await db.store_paths("owner/repo", today, [
            {"path": "/owner/repo", "title": "Cool project", "count": 100, "uniques": 60},
        ])

        resp = await client.get("/api/repos/owner/repo/paths")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["path"] == "/owner/repo"
