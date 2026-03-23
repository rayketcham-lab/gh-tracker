"""Tests for GitHub traffic data collector — the core archival feature.

Specs covered:
1. Fetch and store daily views (total + unique)
2. Fetch and store daily clones (total + unique)
3. Fetch and store top referrers
4. Fetch and store popular paths
5. Idempotent upserts (re-collecting same day doesn't duplicate)
6. ETag caching (304 responses don't waste rate limit)
7. Retry on 202 (stats computation in progress)
8. Rate limit awareness (respect X-RateLimit-Remaining)
9. Multi-repo collection
"""

import json

import pytest

from app.collector import GitHubCollector
from app.database import Database


@pytest.fixture
async def db(tmp_path):
    """Create a temporary database for testing."""
    db_path = tmp_path / "test_metrics.db"
    database = Database(str(db_path))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def collector(db):
    """Create a collector with a test database."""
    return GitHubCollector(
        token="test-token-fake",
        db=db,
        repos=["owner/repo"],
    )


# --- Spec 1: Fetch and store daily views ---


class TestViewsCollection:
    async def test_stores_daily_views(self, collector, db, httpx_mock):
        """Collector fetches /traffic/views and stores daily breakdown."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json={
                "count": 100,
                "uniques": 50,
                "views": [
                    {"timestamp": "2026-03-20T00:00:00Z", "count": 40, "uniques": 20},
                    {"timestamp": "2026-03-21T00:00:00Z", "count": 60, "uniques": 30},
                ],
            },
            headers={"ETag": '"abc123"', "X-RateLimit-Remaining": "4999"},
        )

        await collector.collect_views("owner/repo")

        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-21")
        assert len(rows) == 2
        assert rows[0]["views"] == 40
        assert rows[0]["unique_visitors"] == 20
        assert rows[1]["views"] == 60
        assert rows[1]["unique_visitors"] == 30


# --- Spec 2: Fetch and store daily clones ---


class TestClonesCollection:
    async def test_stores_daily_clones(self, collector, db, httpx_mock):
        """Collector fetches /traffic/clones and stores daily breakdown."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/clones?per=day",
            json={
                "count": 25,
                "uniques": 10,
                "clones": [
                    {"timestamp": "2026-03-20T00:00:00Z", "count": 10, "uniques": 5},
                    {"timestamp": "2026-03-21T00:00:00Z", "count": 15, "uniques": 5},
                ],
            },
            headers={"ETag": '"def456"', "X-RateLimit-Remaining": "4998"},
        )

        await collector.collect_clones("owner/repo")

        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-21")
        assert len(rows) == 2
        assert rows[0]["clones"] == 10
        assert rows[0]["unique_cloners"] == 5
        assert rows[1]["clones"] == 15
        assert rows[1]["unique_cloners"] == 5


# --- Spec 3: Fetch and store top referrers ---


class TestReferrersCollection:
    async def test_stores_referrers(self, collector, db, httpx_mock):
        """Collector fetches /traffic/popular/referrers and stores them."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/popular/referrers",
            json=[
                {"referrer": "google.com", "count": 50, "uniques": 30},
                {"referrer": "news.ycombinator.com", "count": 20, "uniques": 15},
            ],
            headers={"X-RateLimit-Remaining": "4997"},
        )

        await collector.collect_referrers("owner/repo")

        rows = await db.get_referrers("owner/repo")
        assert len(rows) == 2
        assert rows[0]["referrer"] == "google.com"
        assert rows[0]["views"] == 50
        assert rows[1]["referrer"] == "news.ycombinator.com"


# --- Spec 4: Fetch and store popular paths ---


class TestPathsCollection:
    async def test_stores_paths(self, collector, db, httpx_mock):
        """Collector fetches /traffic/popular/paths and stores them."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/popular/paths",
            json=[
                {
                    "path": "/owner/repo",
                    "title": "owner/repo: A cool project",
                    "count": 100,
                    "uniques": 60,
                },
            ],
            headers={"X-RateLimit-Remaining": "4996"},
        )

        await collector.collect_paths("owner/repo")

        rows = await db.get_popular_paths("owner/repo")
        assert len(rows) == 1
        assert rows[0]["path"] == "/owner/repo"
        assert rows[0]["views"] == 100


# --- Spec 5: Idempotent upserts ---


class TestIdempotentUpserts:
    async def test_upsert_views_same_day(self, collector, db, httpx_mock):
        """Collecting the same day twice updates rather than duplicates."""
        response_json = {
            "count": 40,
            "uniques": 20,
            "views": [
                {"timestamp": "2026-03-20T00:00:00Z", "count": 40, "uniques": 20},
            ],
        }
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json=response_json,
            headers={"ETag": '"v1"', "X-RateLimit-Remaining": "4999"},
        )

        await collector.collect_views("owner/repo")

        # Second collection with updated numbers
        response_json["views"][0]["count"] = 45
        response_json["views"][0]["uniques"] = 22
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json=response_json,
            headers={"ETag": '"v2"', "X-RateLimit-Remaining": "4998"},
        )

        await collector.collect_views("owner/repo")

        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-20")
        assert len(rows) == 1
        assert rows[0]["views"] == 45
        assert rows[0]["unique_visitors"] == 22


# --- Spec 6: ETag caching ---


class TestETagCaching:
    async def test_sends_etag_on_subsequent_request(self, collector, db, httpx_mock):
        """Collector stores ETags and sends If-None-Match on next request."""
        # First request — returns data with ETag
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json={"count": 10, "uniques": 5, "views": []},
            headers={"ETag": '"cached-etag"', "X-RateLimit-Remaining": "4999"},
        )
        await collector.collect_views("owner/repo")

        # Second request — should send If-None-Match, gets 304
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            status_code=304,
            headers={"X-RateLimit-Remaining": "4999"},
        )
        await collector.collect_views("owner/repo")

        requests = httpx_mock.get_requests()
        assert len(requests) == 2
        assert requests[1].headers.get("If-None-Match") == '"cached-etag"'

    async def test_304_does_not_overwrite_data(self, collector, db, httpx_mock):
        """A 304 response preserves existing stored data."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json={
                "count": 10,
                "uniques": 5,
                "views": [
                    {"timestamp": "2026-03-20T00:00:00Z", "count": 10, "uniques": 5},
                ],
            },
            headers={"ETag": '"e1"', "X-RateLimit-Remaining": "4999"},
        )
        await collector.collect_views("owner/repo")

        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            status_code=304,
            headers={"X-RateLimit-Remaining": "4999"},
        )
        await collector.collect_views("owner/repo")

        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-20")
        assert len(rows) == 1
        assert rows[0]["views"] == 10


# --- Spec 7: Retry on 202 ---


class TestRetryOn202:
    async def test_retries_on_202_then_succeeds(self, collector, db, httpx_mock):
        """Stats endpoints return 202 when computing — collector retries."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            status_code=202,
            json={},
            headers={"X-RateLimit-Remaining": "4999"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json={
                "count": 10,
                "uniques": 5,
                "views": [
                    {"timestamp": "2026-03-20T00:00:00Z", "count": 10, "uniques": 5},
                ],
            },
            headers={"ETag": '"r1"', "X-RateLimit-Remaining": "4998"},
        )

        await collector.collect_views("owner/repo")

        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-20")
        assert len(rows) == 1
        assert rows[0]["views"] == 10


# --- Spec 8: Rate limit awareness ---


class TestRateLimitAwareness:
    async def test_tracks_remaining_rate_limit(self, collector, httpx_mock):
        """Collector tracks X-RateLimit-Remaining from responses."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/traffic/views?per=day",
            json={"count": 0, "uniques": 0, "views": []},
            headers={"ETag": '"rl1"', "X-RateLimit-Remaining": "100"},
        )

        await collector.collect_views("owner/repo")
        assert collector.rate_limit_remaining == 100

    async def test_stops_when_rate_limit_low(self, collector):
        """Collector refuses to make requests when rate limit is critically low."""
        collector.rate_limit_remaining = 5

        # Should raise when rate limit is too low — no HTTP request made
        with pytest.raises(Exception, match="[Rr]ate limit"):
            await collector.collect_views("owner/repo")


# --- Spec 9: Multi-repo collection ---


class TestMultiRepoCollection:
    async def test_collects_all_repos(self, db, httpx_mock):
        """Collector iterates over all configured repos."""
        collector = GitHubCollector(
            token="test-token",
            db=db,
            repos=["owner/repo1", "owner/repo2"],
        )

        for repo in ["repo1", "repo2"]:
            # Traffic endpoints (4)
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/traffic/views?per=day",
                json={"count": 10, "uniques": 5, "views": []},
                headers={"ETag": f'"{repo}-v"', "X-RateLimit-Remaining": "4990"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/traffic/clones?per=day",
                json={"count": 5, "uniques": 2, "clones": []},
                headers={"ETag": f'"{repo}-c"', "X-RateLimit-Remaining": "4989"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/traffic/popular/referrers",
                json=[],
                headers={"X-RateLimit-Remaining": "4988"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/traffic/popular/paths",
                json=[],
                headers={"X-RateLimit-Remaining": "4987"},
            )
            # People endpoints (4)
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/stargazers",
                json=[],
                headers={"X-RateLimit-Remaining": "4986"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/subscribers",
                json=[],
                headers={"X-RateLimit-Remaining": "4985"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/forks?sort=newest",
                json=[],
                headers={"X-RateLimit-Remaining": "4984"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/stats/contributors",
                json=[],
                headers={"X-RateLimit-Remaining": "4983"},
            )
            # Issues endpoints (2: open + closed)
            for state in ("open", "closed"):
                httpx_mock.add_response(
                    url=f"https://api.github.com/repos/owner/{repo}/issues?state={state}&per_page=30&sort=updated",
                    json=[],
                    headers={"X-RateLimit-Remaining": "4982"},
                )
            # Metadata endpoints (4: repo info, commits, releases, languages)
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}",
                json={
                    "description": "Test", "language": "Python",
                    "stargazers_count": 5, "forks_count": 1,
                    "subscribers_count": 2, "open_issues_count": 0,
                    "size": 100, "license": None, "topics": [],
                    "created_at": "2023-01-01T00:00:00Z",
                    "updated_at": "2026-01-01T00:00:00Z",
                    "pushed_at": "2026-01-01T00:00:00Z",
                    "default_branch": "main", "homepage": "",
                },
                headers={"X-RateLimit-Remaining": "4981"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/commits?per_page=1",
                json=[{}],
                headers={"X-RateLimit-Remaining": "4980"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/releases?per_page=1",
                json=[],
                headers={"X-RateLimit-Remaining": "4979"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/languages",
                json={"Python": 1000},
                headers={"X-RateLimit-Remaining": "4978"},
            )
            # New stats endpoints (4)
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/stats/commit_activity",
                json=[],
                headers={"X-RateLimit-Remaining": "4977"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/stats/code_frequency",
                json=[],
                headers={"X-RateLimit-Remaining": "4976"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/community/profile",
                json={"health_percentage": 75},
                headers={"X-RateLimit-Remaining": "4975"},
            )
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/{repo}/releases?per_page=100",
                json=[],
                headers={"X-RateLimit-Remaining": "4974"},
            )

        # GraphQL summary (called once after the per-repo loop)
        httpx_mock.add_response(
            url="https://api.github.com/graphql",
            method="POST",
            json={
                "data": {
                    "repo0": {
                        "stargazerCount": 5, "forkCount": 1,
                        "issues": {"totalCount": 0},
                        "pullRequests": {"totalCount": 0},
                        "releases": {"totalCount": 0},
                        "discussions": {"totalCount": 0},
                    },
                    "repo1": {
                        "stargazerCount": 5, "forkCount": 1,
                        "issues": {"totalCount": 0},
                        "pullRequests": {"totalCount": 0},
                        "releases": {"totalCount": 0},
                        "discussions": {"totalCount": 0},
                    },
                }
            },
            headers={"X-RateLimit-Remaining": "4973"},
        )

        await collector.collect_all()

        # 4 traffic + 4 people + 2 issues + 4 metadata + 4 new stats = 18 per repo x 2 repos
        # + 1 GraphQL call = 37
        assert len(httpx_mock.get_requests()) == 37


# --- Database schema tests ---


class TestDatabaseSchema:
    async def test_initialize_creates_tables(self, tmp_path):
        """Database.initialize() creates the required tables."""
        db = Database(str(tmp_path / "schema_test.db"))
        await db.initialize()

        tables = await db.list_tables()
        assert "daily_metrics" in tables
        assert "referrers" in tables
        assert "popular_paths" in tables
        assert "etag_cache" in tables
        assert "raw_responses" in tables

        await db.close()

    async def test_upsert_daily_metrics(self, db):
        """Upsert inserts new row then updates existing."""
        await db.upsert_daily_metrics("owner/repo", "2026-03-20", views=10, unique_visitors=5)
        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-20")
        assert rows[0]["views"] == 10

        await db.upsert_daily_metrics("owner/repo", "2026-03-20", views=15, unique_visitors=8)
        rows = await db.get_daily_metrics("owner/repo", "2026-03-20", "2026-03-20")
        assert len(rows) == 1
        assert rows[0]["views"] == 15

    async def test_store_raw_response(self, db):
        """Raw API responses are stored for auditability."""
        raw = {"count": 10, "uniques": 5, "views": []}
        await db.store_raw_response("owner/repo", "traffic/views", json.dumps(raw))

        stored = await db.get_raw_responses("owner/repo", "traffic/views")
        assert len(stored) >= 1
        assert json.loads(stored[0]["response_body"]) == raw
