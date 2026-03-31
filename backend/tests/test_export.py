"""Tests for data export endpoints.

Specs: Issue #22
1. GET /api/export/traffic?format=csv returns CSV with Content-Disposition
2. GET /api/export/traffic?format=json returns JSON array
3. GET /api/export/people?format=csv returns CSV with headers
4. GET /api/export/people?format=json returns JSON with stargazers+contributors
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_export.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestTrafficExport:
    async def test_csv_export_has_content_disposition(self, client, db):
        await db.upsert_daily_metrics("a/b", "2026-03-20", views=10, unique_visitors=5)
        resp = await client.get("/api/export/traffic?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        lines = resp.text.strip().split("\n")
        assert len(lines) >= 2  # header + data row

    async def test_json_export_returns_array(self, client, db):
        await db.upsert_daily_metrics("a/b", "2026-03-20", views=10, unique_visitors=5)
        resp = await client.get("/api/export/traffic?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 1

    async def test_csv_empty_returns_empty_csv(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        assert resp.status_code == 200


class TestPeopleExport:
    async def test_csv_export_has_headers(self, client, db):
        await db.upsert_stargazer("a/b", "testuser", "2026-03-20")
        resp = await client.get("/api/export/people?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers.get("content-type", "")
        lines = resp.text.strip().split("\n")
        assert "repo_name" in lines[0]
        assert "testuser" in resp.text

    async def test_json_export_returns_structure(self, client, db):
        await db.upsert_stargazer("a/b", "testuser", "2026-03-20")
        resp = await client.get("/api/export/people?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert "stargazers" in data
        assert "contributors" in data
