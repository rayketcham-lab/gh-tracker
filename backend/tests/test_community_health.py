"""Tests for community health score collector (Issue #14).

Specs:
1. collect_community_profile fetches /community/profile endpoint
2. Stores health_percentage in repo_metadata
3. health_percentage is returned in the metadata API endpoint
4. None response handled gracefully
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_health.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def collector(db):
    return GitHubCollector(
        token="test-token-fake",
        db=db,
        repos=["owner/repo"],
    )


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestCollectCommunityProfile:
    async def test_stores_health_percentage(self, collector, db, httpx_mock):
        """collect_community_profile stores health_percentage in repo_metadata."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/community/profile",
            json={
                "health_percentage": 83,
                "description": "A test repo",
                "documentation": None,
                "files": {
                    "code_of_conduct": None,
                    "contributing": {"url": "https://github.com/owner/repo/blob/main/CONTRIBUTING.md"},
                    "issue_template": None,
                    "pull_request_template": None,
                    "license": {"url": "https://github.com/owner/repo/blob/main/LICENSE"},
                    "readme": {"url": "https://github.com/owner/repo/blob/main/README.md"},
                },
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_community_profile("owner/repo")

        meta = await db.get_repo_metadata("owner/repo")
        assert meta is not None
        assert meta["health_percentage"] == 83

    async def test_none_response_skipped(self, collector, db, httpx_mock):
        """304 / None response does not raise and nothing is stored."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/community/profile",
            status_code=304,
            headers={"X-RateLimit-Remaining": "4990"},
        )
        # Should not raise
        await collector.collect_community_profile("owner/repo")
        meta = await db.get_repo_metadata("owner/repo")
        assert meta is None

    async def test_zero_health_percentage(self, collector, db, httpx_mock):
        """health_percentage of 0 is stored correctly (not confused with missing)."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/community/profile",
            json={"health_percentage": 0},
            headers={"X-RateLimit-Remaining": "4990"},
        )
        await collector.collect_community_profile("owner/repo")
        meta = await db.get_repo_metadata("owner/repo")
        assert meta is not None
        assert meta["health_percentage"] == 0


class TestHealthPercentageInDB:
    async def test_health_percentage_column_exists(self, db):
        """health_percentage column is present after table creation."""
        await db.upsert_repo_metadata("owner/repo", health_percentage=75)
        meta = await db.get_repo_metadata("owner/repo")
        assert meta is not None
        assert "health_percentage" in meta
        assert meta["health_percentage"] == 75

    async def test_health_percentage_defaults_to_zero(self, db):
        """When not explicitly set, health_percentage defaults to 0."""
        await db.upsert_repo_metadata("owner/repo", stars=10)
        meta = await db.get_repo_metadata("owner/repo")
        assert meta is not None
        assert meta["health_percentage"] == 0

    async def test_health_percentage_updatable(self, db):
        """health_percentage can be updated via upsert."""
        await db.upsert_repo_metadata("owner/repo", health_percentage=50)
        await db.upsert_repo_metadata("owner/repo", health_percentage=95)
        meta = await db.get_repo_metadata("owner/repo")
        assert meta["health_percentage"] == 95


class TestHealthPercentageInAPI:
    async def test_metadata_endpoint_includes_health_percentage(self, client, db):
        """GET /metadata includes health_percentage field."""
        await db.upsert_repo_metadata(
            "owner/repo",
            stars=10,
            health_percentage=78,
        )
        resp = await client.get("/api/repos/owner/repo/metadata")
        assert resp.status_code == 200
        data = resp.json()
        assert "health_percentage" in data
        assert data["health_percentage"] == 78

    async def test_metadata_endpoint_unknown_repo_has_health_field(self, client):
        """Unknown repo default response includes health_percentage."""
        resp = await client.get("/api/repos/nobody/empty/metadata")
        assert resp.status_code == 200
        data = resp.json()
        # The default response dict should include health_percentage
        assert "health_percentage" in data
