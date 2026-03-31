"""Tests for branch protection API. Issue #34."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_bp.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestBranchesEndpoint:
    async def test_list_branches_empty(self, client):
        resp = await client.get("/api/repos/no/exist/branches")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_branches_with_data(self, client, db):
        await db._db.execute(
            """INSERT INTO branches
               (repo_name, name, protected, protection_json)
               VALUES (?, ?, ?, ?)""",
            ("a/b", "main", 1, '{"required_reviews": 2}')
        )
        await db._db.commit()
        resp = await client.get("/api/repos/a/b/branches")
        assert resp.status_code == 200
        branches = resp.json()
        assert len(branches) == 1
        assert branches[0]["name"] == "main"
        assert branches[0]["protected"] == 1

    async def test_multiple_branches_sorted(self, client, db):
        for name in ("develop", "main", "feature/x"):
            await db._db.execute(
                """INSERT INTO branches
                   (repo_name, name, protected, protection_json)
                   VALUES (?, ?, ?, ?)""",
                ("a/b", name, 0, '{}')
            )
        await db._db.commit()
        resp = await client.get("/api/repos/a/b/branches")
        names = [b["name"] for b in resp.json()]
        assert names == sorted(names)
