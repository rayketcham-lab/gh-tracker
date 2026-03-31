"""Tests for PR command center API. Issue #33."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_prs.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestOpenPRsEndpoint:
    async def test_get_open_prs_empty(self, client):
        resp = await client.get("/api/prs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_open_prs_with_data(self, client, db):
        await db.upsert_issue("a/b", 1, "Fix bug", "open", "dev", "bug",
                              "2026-03-20", None, is_pr=True)
        await db.upsert_issue("a/b", 2, "Add feature", "open", "dev2", "",
                              "2026-03-20", None, is_pr=True)
        await db.upsert_issue("a/b", 3, "Not a PR", "open", "dev", "",
                              "2026-03-20", None, is_pr=False)
        resp = await client.get("/api/prs")
        prs = resp.json()
        assert len(prs) == 2
        assert all(p["is_pr"] for p in prs)

    async def test_filter_by_repo(self, client, db):
        await db.upsert_issue("a/b", 1, "PR1", "open", "dev", "",
                              "2026-03-20", None, is_pr=True)
        await db.upsert_issue("c/d", 2, "PR2", "open", "dev", "",
                              "2026-03-20", None, is_pr=True)
        resp = await client.get("/api/prs?repo=a/b")
        prs = resp.json()
        assert len(prs) == 1
        assert prs[0]["repo_name"] == "a/b"

    async def test_only_open_prs(self, client, db):
        await db.upsert_issue("a/b", 1, "Open PR", "open", "dev", "",
                              "2026-03-20", None, is_pr=True)
        await db.upsert_issue("a/b", 2, "Closed PR", "closed", "dev", "",
                              "2026-03-20", "2026-03-21", is_pr=True)
        resp = await client.get("/api/prs")
        prs = resp.json()
        assert len(prs) == 1
        assert prs[0]["title"] == "Open PR"
