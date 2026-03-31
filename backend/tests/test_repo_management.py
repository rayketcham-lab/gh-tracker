"""Tests for dynamic repo management.

Specs: Issue #24
1. POST /api/repos with {"repo_name": "owner/repo"} adds it to tracked repos
2. DELETE /api/repos/{owner}/{repo} removes it
3. GET /api/repos returns both env-var repos and DB-stored repos
4. Adding duplicate repo is idempotent (no error)
5. Deleting non-existent repo returns 404
"""

import pytest
from httpx import ASGITransport, AsyncClient
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_mgmt.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestAddRepo:
    async def test_add_repo_returns_201(self, client):
        resp = await client.post("/api/repos", json={"repo_name": "test/repo"})
        assert resp.status_code == 201
        assert resp.json()["repo_name"] == "test/repo"

    async def test_added_repo_appears_in_list(self, client):
        await client.post("/api/repos", json={"repo_name": "test/repo"})
        resp = await client.get("/api/repos")
        assert "test/repo" in resp.json()

    async def test_add_duplicate_is_idempotent(self, client):
        await client.post("/api/repos", json={"repo_name": "test/repo"})
        resp = await client.post("/api/repos", json={"repo_name": "test/repo"})
        assert resp.status_code in (200, 201)

    async def test_add_invalid_format_returns_422(self, client):
        resp = await client.post("/api/repos", json={"repo_name": "noslash"})
        assert resp.status_code == 422


class TestDeleteRepo:
    async def test_delete_tracked_repo(self, client):
        await client.post("/api/repos", json={"repo_name": "test/repo"})
        resp = await client.delete("/api/repos/test/repo")
        assert resp.status_code == 200

    async def test_deleted_repo_gone_from_list(self, client):
        await client.post("/api/repos", json={"repo_name": "test/repo"})
        await client.delete("/api/repos/test/repo")
        resp = await client.get("/api/repos")
        assert "test/repo" not in resp.json()

    async def test_delete_nonexistent_returns_404(self, client):
        resp = await client.delete("/api/repos/no/exist")
        assert resp.status_code == 404
