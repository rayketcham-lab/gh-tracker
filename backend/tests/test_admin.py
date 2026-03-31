"""Tests for admin endpoints: backup and collection status.

Specs: Issue #35
1. GET /api/admin/backup returns SQLite DB as downloadable file
2. GET /api/admin/status returns DB size, table row counts, last collection time
"""
import pytest
from httpx import ASGITransport, AsyncClient
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_admin.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestBackupEndpoint:
    async def test_backup_returns_sqlite_file(self, client):
        resp = await client.get("/api/admin/backup")
        assert resp.status_code == 200
        assert "application/octet-stream" in resp.headers.get("content-type", "")
        assert "attachment" in resp.headers.get("content-disposition", "")
        # SQLite files start with "SQLite format 3\x00"
        assert resp.content[:16].startswith(b"SQLite format 3")


class TestStatusEndpoint:
    async def test_status_returns_db_info(self, client, db):
        await db.upsert_daily_metrics("a/b", "2026-03-20", views=10, unique_visitors=5)
        resp = await client.get("/api/admin/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "db_size_bytes" in data
        assert "tables" in data
        assert "daily_metrics" in data["tables"]
        assert data["tables"]["daily_metrics"] >= 1
