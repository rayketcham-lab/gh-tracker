"""Tests for CSV/JSON export endpoints (Issue #20).

Specs:
1. GET /api/export/traffic?format=json — returns all daily_metrics as JSON
2. GET /api/export/traffic?format=csv — returns CSV with headers
3. GET /api/export/people?format=json — returns stargazers + contributors as JSON
4. GET /api/export/people?format=csv — returns CSV with stargazers and contributors
5. Empty DB returns empty payload gracefully
"""

import csv
import io

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
async def seeded_db(db):
    """DB pre-populated with traffic and people data."""
    await db.upsert_daily_metrics("owner/repo1", "2026-03-20",
                                  views=100, unique_visitors=50,
                                  clones=10, unique_cloners=5)
    await db.upsert_daily_metrics("owner/repo1", "2026-03-21",
                                  views=80, unique_visitors=40,
                                  clones=8, unique_cloners=4)
    await db.upsert_daily_metrics("owner/repo2", "2026-03-20",
                                  views=200, unique_visitors=120)

    await db.upsert_stargazer("owner/repo1", "alice", "2026-03-15T10:00:00Z")
    await db.upsert_stargazer("owner/repo1", "bob", "2026-03-18T14:30:00Z")
    await db.upsert_contributor("owner/repo1", "alice", commits=42,
                                additions=1500, deletions=300)
    return db


@pytest.fixture
async def client(seeded_db):
    app = create_app(db=seeded_db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest.fixture
async def empty_client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestTrafficExportJSON:
    async def test_returns_all_rows_as_json(self, client):
        resp = await client.get("/api/export/traffic?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) == 3

    async def test_json_rows_have_expected_fields(self, client):
        resp = await client.get("/api/export/traffic?format=json")
        data = resp.json()
        row = data[0]
        assert "repo_name" in row
        assert "date" in row
        assert "views" in row
        assert "unique_visitors" in row

    async def test_default_format_is_json(self, client):
        """No format param defaults to JSON."""
        resp = await client.get("/api/export/traffic")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)

    async def test_empty_db_returns_empty_list(self, empty_client):
        resp = await empty_client.get("/api/export/traffic?format=json")
        assert resp.status_code == 200
        assert resp.json() == []


class TestTrafficExportCSV:
    async def test_returns_csv_content_type(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_csv_has_header_row(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        text = resp.text
        reader = csv.reader(io.StringIO(text))
        header = next(reader)
        assert "repo_name" in header
        assert "date" in header
        assert "views" in header

    async def test_csv_has_correct_row_count(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        text = resp.text
        reader = csv.DictReader(io.StringIO(text))
        rows = list(reader)
        assert len(rows) == 3

    async def test_csv_values_correct(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        # Find the row for repo1 on 2026-03-20
        row = next(r for r in rows if r["repo_name"] == "owner/repo1" and r["date"] == "2026-03-20")
        assert int(row["views"]) == 100
        assert int(row["unique_visitors"]) == 50

    async def test_empty_db_returns_empty_csv(self, empty_client):
        resp = await empty_client.get("/api/export/traffic?format=csv")
        assert resp.status_code == 200
        assert resp.text == ""

    async def test_content_disposition_header(self, client):
        resp = await client.get("/api/export/traffic?format=csv")
        assert "attachment" in resp.headers.get("content-disposition", "")


class TestPeopleExportJSON:
    async def test_returns_stargazers_and_contributors(self, client):
        resp = await client.get("/api/export/people?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert "stargazers" in data
        assert "contributors" in data

    async def test_stargazers_count(self, client):
        resp = await client.get("/api/export/people?format=json")
        data = resp.json()
        assert len(data["stargazers"]) == 2

    async def test_contributors_count(self, client):
        resp = await client.get("/api/export/people?format=json")
        data = resp.json()
        assert len(data["contributors"]) == 1

    async def test_stargazer_fields(self, client):
        resp = await client.get("/api/export/people?format=json")
        data = resp.json()
        star = data["stargazers"][0]
        assert "repo_name" in star
        assert "username" in star
        assert "starred_at" in star

    async def test_contributor_fields(self, client):
        resp = await client.get("/api/export/people?format=json")
        data = resp.json()
        contrib = data["contributors"][0]
        assert "repo_name" in contrib
        assert "username" in contrib
        assert "commits" in contrib
        assert "additions" in contrib
        assert "deletions" in contrib

    async def test_empty_db_returns_empty_lists(self, empty_client):
        resp = await empty_client.get("/api/export/people?format=json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["stargazers"] == []
        assert data["contributors"] == []


class TestPeopleExportCSV:
    async def test_returns_csv_content_type(self, client):
        resp = await client.get("/api/export/people?format=csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.headers["content-type"]

    async def test_csv_has_header_row(self, client):
        resp = await client.get("/api/export/people?format=csv")
        reader = csv.reader(io.StringIO(resp.text))
        header = next(reader)
        assert "repo_name" in header
        assert "username" in header
        assert "type" in header

    async def test_csv_contains_stargazers_and_contributors(self, client):
        resp = await client.get("/api/export/people?format=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        types = {r["type"] for r in rows}
        assert "stargazer" in types
        assert "contributor" in types

    async def test_csv_total_rows(self, client):
        """2 stargazers + 1 contributor = 3 data rows."""
        resp = await client.get("/api/export/people?format=csv")
        reader = csv.DictReader(io.StringIO(resp.text))
        rows = list(reader)
        assert len(rows) == 3

    async def test_content_disposition_header(self, client):
        resp = await client.get("/api/export/people?format=csv")
        assert "attachment" in resp.headers.get("content-disposition", "")

    async def test_empty_db_produces_header_only_csv(self, empty_client):
        resp = await empty_client.get("/api/export/people?format=csv")
        assert resp.status_code == 200
        # Should have at least the header row with no data rows
        reader = csv.reader(io.StringIO(resp.text))
        rows = list(reader)
        # Header only (1 row) or empty
        assert len(rows) <= 1
