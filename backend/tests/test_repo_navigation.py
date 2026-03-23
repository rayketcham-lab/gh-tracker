"""Tests for repo navigation — switching between repos and getting their data.

Bug: clicking repos in visitors table does nothing visible.
Root cause: no repo detail endpoint, no way to get all data for a repo at once.

Specs:
1. GET /api/repos/{owner}/{repo}/summary returns combined overview for one repo
2. Summary includes traffic, referrers, paths, and metadata
3. Summary works for repos with zero traffic
4. Summary includes github_url for linking
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_nav.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def seeded_db(db):
    await db.upsert_daily_metrics(
        "owner/repo1", "2026-03-20", views=50, unique_visitors=20, clones=5, unique_cloners=2
    )
    await db.upsert_daily_metrics(
        "owner/repo1", "2026-03-21", views=80, unique_visitors=35, clones=10, unique_cloners=4
    )
    await db.store_referrers("owner/repo1", "2026-03-21", [
        {"referrer": "google.com", "count": 30, "uniques": 20},
    ])
    await db.store_paths("owner/repo1", "2026-03-21", [
        {"path": "/owner/repo1", "title": "repo1", "count": 50, "uniques": 25},
    ])
    return db


@pytest.fixture
async def client(seeded_db):
    app = create_app(db=seeded_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRepoSummary:
    async def test_summary_returns_combined_data(self, client):
        """GET /api/repos/{owner}/{repo}/summary returns all data for a repo."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        assert resp.status_code == 200
        data = resp.json()

        assert "traffic" in data
        assert "referrers" in data
        assert "paths" in data
        assert "github_url" in data
        assert "repo_name" in data

    async def test_summary_has_correct_github_url(self, client):
        """Summary includes the correct GitHub URL."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        data = resp.json()
        assert data["github_url"] == "https://github.com/owner/repo1"
        assert data["repo_name"] == "owner/repo1"

    async def test_summary_traffic_data(self, client):
        """Summary includes traffic time series."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        data = resp.json()
        assert len(data["traffic"]) == 2
        assert data["traffic"][0]["views"] == 50

    async def test_summary_referrers_data(self, client):
        """Summary includes referrers."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        data = resp.json()
        assert len(data["referrers"]) >= 1
        assert data["referrers"][0]["referrer"] == "google.com"

    async def test_summary_paths_data(self, client):
        """Summary includes popular paths."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        data = resp.json()
        assert len(data["paths"]) >= 1

    async def test_summary_empty_repo(self, client, seeded_db):
        """Summary works for repos with no data — returns empty arrays."""
        resp = await client.get("/api/repos/nobody/empty/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["traffic"] == []
        assert data["referrers"] == []
        assert data["paths"] == []
        assert data["github_url"] == "https://github.com/nobody/empty"

    async def test_summary_includes_totals(self, client):
        """Summary includes computed totals for quick display."""
        resp = await client.get("/api/repos/owner/repo1/summary")
        data = resp.json()
        assert "total_views" in data
        assert "total_unique_visitors" in data
        assert data["total_views"] == 130  # 50 + 80
        assert data["total_unique_visitors"] == 55  # 20 + 35
