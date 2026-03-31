"""Tests for repo settings write operations.

Specs: Issue #28
1. PATCH /api/repos/{owner}/{repo}/settings proxies to GitHub API
2. Returns 503 when no GH token configured
3. Returns 422 when no fields provided
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_settings.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestRepoSettingsEndpoint:
    async def test_endpoint_exists_returns_503_without_token(self, client):
        """PATCH should exist; returns 503 when no GH_TOKEN set."""
        resp = await client.patch(
            "/api/repos/test/repo/settings",
            json={"description": "new desc"},
        )
        assert resp.status_code == 503
        assert "token" in resp.json()["detail"].lower()

    async def test_empty_body_returns_422(self, client):
        """Must provide at least one field to update."""
        resp = await client.patch(
            "/api/repos/test/repo/settings",
            json={},
        )
        assert resp.status_code == 422
