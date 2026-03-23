"""Tests for repository statistics — commit activity and code frequency (Issue #4).

Specs:
1. collect_commit_activity stores 52-week commit data
2. collect_code_frequency stores weekly additions/deletions
3. DB methods upsert and retrieve correctly
4. API endpoints return data
5. 202 retry and None responses handled gracefully
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_stats.db"))
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


# --- DB layer tests ---


class TestCommitActivityDB:
    async def test_upsert_and_retrieve(self, db):
        days = json.dumps([0, 1, 2, 3, 4, 5, 6])
        await db.upsert_commit_activity("owner/repo", 1700000000, days, 21)
        rows = await db.get_commit_activity("owner/repo")
        assert len(rows) == 1
        assert rows[0]["week_timestamp"] == 1700000000
        assert rows[0]["total"] == 21
        assert json.loads(rows[0]["days"]) == [0, 1, 2, 3, 4, 5, 6]

    async def test_upsert_is_idempotent(self, db):
        days = json.dumps([1] * 7)
        await db.upsert_commit_activity("owner/repo", 1700000000, days, 7)
        await db.upsert_commit_activity("owner/repo", 1700000000, days, 14)
        rows = await db.get_commit_activity("owner/repo")
        assert len(rows) == 1
        assert rows[0]["total"] == 14

    async def test_multiple_weeks_sorted_by_timestamp(self, db):
        await db.upsert_commit_activity("owner/repo", 1700000000, "[]", 5)
        await db.upsert_commit_activity("owner/repo", 1699000000, "[]", 3)
        rows = await db.get_commit_activity("owner/repo")
        assert rows[0]["week_timestamp"] < rows[1]["week_timestamp"]

    async def test_empty_returns_empty_list(self, db):
        rows = await db.get_commit_activity("nobody/nothing")
        assert rows == []


class TestCodeFrequencyDB:
    async def test_upsert_and_retrieve(self, db):
        await db.upsert_code_frequency("owner/repo", 1700000000, 500, 100)
        rows = await db.get_code_frequency("owner/repo")
        assert len(rows) == 1
        assert rows[0]["additions"] == 500
        assert rows[0]["deletions"] == 100

    async def test_upsert_is_idempotent(self, db):
        await db.upsert_code_frequency("owner/repo", 1700000000, 100, 20)
        await db.upsert_code_frequency("owner/repo", 1700000000, 200, 50)
        rows = await db.get_code_frequency("owner/repo")
        assert len(rows) == 1
        assert rows[0]["additions"] == 200

    async def test_multiple_weeks_sorted(self, db):
        await db.upsert_code_frequency("owner/repo", 1700000000, 100, 10)
        await db.upsert_code_frequency("owner/repo", 1699000000, 50, 5)
        rows = await db.get_code_frequency("owner/repo")
        assert rows[0]["week_timestamp"] < rows[1]["week_timestamp"]


# --- Collector tests ---


class TestCollectCommitActivity:
    async def test_stores_weekly_data(self, collector, db, httpx_mock):
        """collect_commit_activity stores each week row."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/commit_activity",
            json=[
                {"week": 1700000000, "days": [0, 2, 3, 1, 4, 5, 6], "total": 21},
                {"week": 1700604800, "days": [1, 1, 1, 1, 1, 1, 1], "total": 7},
            ],
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_commit_activity("owner/repo")

        rows = await db.get_commit_activity("owner/repo")
        assert len(rows) == 2
        assert rows[0]["total"] == 21
        assert rows[1]["total"] == 7

    async def test_none_response_skipped(self, collector, db, httpx_mock):
        """202 response (turns into None) does not raise."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/commit_activity",
            status_code=202,
            json={},
            headers={"X-RateLimit-Remaining": "4990"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/commit_activity",
            status_code=202,
            json={},
            headers={"X-RateLimit-Remaining": "4990"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/commit_activity",
            status_code=202,
            json={},
            headers={"X-RateLimit-Remaining": "4990"},
        )
        # Should not raise, no rows stored
        await collector.collect_commit_activity("owner/repo")
        rows = await db.get_commit_activity("owner/repo")
        assert rows == []


class TestCollectCodeFrequency:
    async def test_stores_additions_and_deletions(self, collector, db, httpx_mock):
        """collect_code_frequency stores additions and absolute deletions."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/code_frequency",
            json=[
                [1700000000, 300, -50],
                [1700604800, 100, -20],
            ],
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_code_frequency("owner/repo")

        rows = await db.get_code_frequency("owner/repo")
        assert len(rows) == 2
        assert rows[0]["additions"] == 300
        assert rows[0]["deletions"] == 50  # abs value

    async def test_non_list_response_skipped(self, collector, db, httpx_mock):
        """Non-list (e.g. empty dict) response does not raise."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/stats/code_frequency",
            json={},
            headers={"X-RateLimit-Remaining": "4990"},
        )
        await collector.collect_code_frequency("owner/repo")
        rows = await db.get_code_frequency("owner/repo")
        assert rows == []


# --- API endpoint tests ---


class TestCommitActivityEndpoint:
    async def test_returns_empty_for_unknown_repo(self, client):
        resp = await client.get("/api/repos/nobody/nothing/commit-activity")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_stored_weeks(self, client, db):
        await db.upsert_commit_activity(
            "owner/repo", 1700000000, json.dumps([0, 1, 2, 3, 4, 5, 6]), 21
        )
        resp = await client.get("/api/repos/owner/repo/commit-activity")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["total"] == 21
        assert data[0]["week_timestamp"] == 1700000000


class TestCodeFrequencyEndpoint:
    async def test_returns_empty_for_unknown_repo(self, client):
        resp = await client.get("/api/repos/nobody/nothing/code-frequency")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_stored_frequency(self, client, db):
        await db.upsert_code_frequency("owner/repo", 1700000000, 500, 100)
        resp = await client.get("/api/repos/owner/repo/code-frequency")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["additions"] == 500
        assert data[0]["deletions"] == 100
