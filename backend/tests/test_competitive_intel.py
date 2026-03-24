"""Tests for competitive intelligence features (Issue #10).

Specs covered:
1. detect_watcher_changes stores 'added' when new watchers appear
2. detect_watcher_changes stores 'removed' when watchers disappear
3. GET /api/repos/{owner}/{repo}/watcher-changes returns change history
4. GET /api/repos/{owner}/{repo}/referrer-trends groups referrers by date
5. Referrer trends show appeared/disappeared sources
6. Empty repo returns empty list for both endpoints
"""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_ci.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# DB-level watcher change tests
# ---------------------------------------------------------------------------


class TestWatcherChangesDB:
    async def test_store_and_retrieve_added(self, db):
        await db.store_watcher_change("owner/repo", "alice", "added")
        changes = await db.get_watcher_changes("owner/repo")
        assert len(changes) == 1
        assert changes[0]["username"] == "alice"
        assert changes[0]["action"] == "added"

    async def test_store_and_retrieve_removed(self, db):
        await db.store_watcher_change("owner/repo", "bob", "removed")
        changes = await db.get_watcher_changes("owner/repo")
        assert any(c["username"] == "bob" and c["action"] == "removed" for c in changes)

    async def test_changes_ordered_newest_first(self, db):
        await db.store_watcher_change("owner/repo", "alice", "added")
        await db.store_watcher_change("owner/repo", "bob", "added")
        changes = await db.get_watcher_changes("owner/repo")
        # Most recent insertion should appear first
        assert changes[0]["username"] == "bob"

    async def test_changes_isolated_by_repo(self, db):
        await db.store_watcher_change("owner/repo1", "alice", "added")
        await db.store_watcher_change("owner/repo2", "bob", "added")
        changes1 = await db.get_watcher_changes("owner/repo1")
        changes2 = await db.get_watcher_changes("owner/repo2")
        assert all(c["username"] == "alice" for c in changes1)
        assert all(c["username"] == "bob" for c in changes2)

    async def test_empty_repo_returns_empty_list(self, db):
        changes = await db.get_watcher_changes("nobody/missing")
        assert changes == []


# ---------------------------------------------------------------------------
# Collector detect_watcher_changes tests
# ---------------------------------------------------------------------------


class TestDetectWatcherChanges:
    async def test_detects_new_watcher(self, db):
        """A watcher not yet in the DB should be stored as 'added'."""
        repo = "owner/repo"
        # DB has no watchers initially

        collector = GitHubCollector(token="tok", db=db, repos=[repo])
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "alice"}]

        with patch.object(collector, "_request", new=AsyncMock(return_value=mock_response)):
            await collector.detect_watcher_changes(repo)

        # alice should now be in watchers table
        watchers = await db.get_watchers(repo)
        assert any(w["username"] == "alice" for w in watchers)

        # change log should record 'added'
        changes = await db.get_watcher_changes(repo)
        assert any(c["username"] == "alice" and c["action"] == "added" for c in changes)

        await collector.close()

    async def test_detects_removed_watcher(self, db):
        """A watcher in the DB but absent from fresh fetch is recorded as 'removed'."""
        repo = "owner/repo"
        await db.upsert_watcher(repo, "alice")
        await db.upsert_watcher(repo, "bob")

        collector = GitHubCollector(token="tok", db=db, repos=[repo])
        # GitHub now only returns alice — bob has un-watched
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "alice"}]

        with patch.object(collector, "_request", new=AsyncMock(return_value=mock_response)):
            await collector.detect_watcher_changes(repo)

        changes = await db.get_watcher_changes(repo)
        assert any(c["username"] == "bob" and c["action"] == "removed" for c in changes)

        await collector.close()

    async def test_no_changes_no_records(self, db):
        """When watchers are unchanged, no change records are created."""
        repo = "owner/repo"
        await db.upsert_watcher(repo, "alice")

        collector = GitHubCollector(token="tok", db=db, repos=[repo])
        mock_response = MagicMock()
        mock_response.json.return_value = [{"login": "alice"}]

        with patch.object(collector, "_request", new=AsyncMock(return_value=mock_response)):
            await collector.detect_watcher_changes(repo)

        changes = await db.get_watcher_changes(repo)
        assert changes == []

        await collector.close()

    async def test_none_response_is_handled_gracefully(self, db):
        """If the API returns None (304/202), no crash and no changes stored."""
        repo = "owner/repo"
        await db.upsert_watcher(repo, "alice")

        collector = GitHubCollector(token="tok", db=db, repos=[repo])
        with patch.object(collector, "_request", new=AsyncMock(return_value=None)):
            await collector.detect_watcher_changes(repo)

        changes = await db.get_watcher_changes(repo)
        assert changes == []

        await collector.close()


# ---------------------------------------------------------------------------
# Referrer trends DB tests
# ---------------------------------------------------------------------------


class TestReferrerTrendsDB:
    async def test_empty_repo_returns_empty(self, db):
        trends = await db.get_referrer_trends("nobody/empty")
        assert trends == []

    async def test_single_date_all_appeared(self, db):
        """On the first date, all referrers are 'appeared'."""
        await db.store_referrers(
            "owner/repo", "2026-03-20",
            [
                {"referrer": "google.com", "count": 50, "uniques": 20},
                {"referrer": "twitter.com", "count": 10, "uniques": 5},
            ],
        )
        trends = await db.get_referrer_trends("owner/repo")
        assert len(trends) == 1
        first = trends[0]
        assert first["date"] == "2026-03-20"
        assert set(first["appeared"]) == {"google.com", "twitter.com"}
        assert first["disappeared"] == []

    async def test_new_referrer_appears(self, db):
        """A referrer present on day 2 but not day 1 is listed in 'appeared'."""
        repo = "owner/repo"
        await db.store_referrers(
            repo, "2026-03-19",
            [{"referrer": "google.com", "count": 30, "uniques": 10}],
        )
        await db.store_referrers(
            repo, "2026-03-20",
            [
                {"referrer": "google.com", "count": 20, "uniques": 8},
                {"referrer": "reddit.com", "count": 5, "uniques": 3},
            ],
        )
        trends = await db.get_referrer_trends(repo)
        day2 = next(t for t in trends if t["date"] == "2026-03-20")
        assert "reddit.com" in day2["appeared"]
        assert "google.com" not in day2["appeared"]

    async def test_referrer_disappears(self, db):
        """A referrer present on day 1 but absent on day 2 is in 'disappeared'."""
        repo = "owner/repo"
        await db.store_referrers(
            repo, "2026-03-19",
            [
                {"referrer": "google.com", "count": 30, "uniques": 10},
                {"referrer": "hackernews.com", "count": 15, "uniques": 7},
            ],
        )
        await db.store_referrers(
            repo, "2026-03-20",
            [{"referrer": "google.com", "count": 25, "uniques": 9}],
        )
        trends = await db.get_referrer_trends(repo)
        day2 = next(t for t in trends if t["date"] == "2026-03-20")
        assert "hackernews.com" in day2["disappeared"]


# ---------------------------------------------------------------------------
# API endpoint tests
# ---------------------------------------------------------------------------


class TestWatcherChangesEndpoint:
    async def test_endpoint_returns_200_empty(self, client):
        resp = await client.get("/api/repos/nobody/empty/watcher-changes")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_endpoint_returns_changes(self, client, db):
        await db.store_watcher_change("owner/repo", "alice", "added")
        resp = await client.get("/api/repos/owner/repo/watcher-changes")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["username"] == "alice"
        assert data[0]["action"] == "added"


class TestReferrerTrendsEndpoint:
    async def test_endpoint_returns_200_empty(self, client):
        resp = await client.get("/api/repos/nobody/empty/referrer-trends")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_endpoint_returns_trends(self, client, db):
        await db.store_referrers(
            "owner/repo", "2026-03-20",
            [{"referrer": "google.com", "count": 40, "uniques": 15}],
        )
        resp = await client.get("/api/repos/owner/repo/referrer-trends")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["date"] == "2026-03-20"
        assert "appeared" in data[0]
        assert "disappeared" in data[0]
        assert "referrers" in data[0]
