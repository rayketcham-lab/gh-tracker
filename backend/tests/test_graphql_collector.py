"""Tests for the GraphQL summary collector (Feature 2 — Issue #2).

Specs:
1. Builds a multi-repo GraphQL query and posts to the endpoint
2. Stores stars, forks, open_issues_count, releases_count from response
3. Handles missing / null repo data gracefully
4. Calls collect_graphql_summary at the end of collect_all
"""

import pytest

from app.collector import GitHubCollector
from app.database import Database

GRAPHQL_URL = "https://api.github.com/graphql"


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_graphql.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def collector(db):
    return GitHubCollector(
        token="test-token-fake",
        db=db,
        repos=["owner/alpha", "owner/beta"],
    )


class TestCollectGraphqlSummary:
    async def test_posts_to_graphql_endpoint(self, collector, db, httpx_mock):
        """collect_graphql_summary POSTs to the GraphQL endpoint."""
        httpx_mock.add_response(
            url=GRAPHQL_URL,
            method="POST",
            json={
                "data": {
                    "repo0": {
                        "stargazerCount": 10,
                        "forkCount": 2,
                        "issues": {"totalCount": 5},
                        "pullRequests": {"totalCount": 1},
                        "releases": {"totalCount": 3},
                        "discussions": {"totalCount": 0},
                    },
                    "repo1": {
                        "stargazerCount": 99,
                        "forkCount": 20,
                        "issues": {"totalCount": 12},
                        "pullRequests": {"totalCount": 4},
                        "releases": {"totalCount": 7},
                        "discussions": {"totalCount": 2},
                    },
                }
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_graphql_summary(["owner/alpha", "owner/beta"])

        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert requests[0].url == GRAPHQL_URL
        assert requests[0].method == "POST"

    async def test_stores_stars_and_forks(self, collector, db, httpx_mock):
        """Stars and forks are stored in repo_metadata from GraphQL response."""
        httpx_mock.add_response(
            url=GRAPHQL_URL,
            method="POST",
            json={
                "data": {
                    "repo0": {
                        "stargazerCount": 42,
                        "forkCount": 7,
                        "issues": {"totalCount": 3},
                        "pullRequests": {"totalCount": 1},
                        "releases": {"totalCount": 2},
                        "discussions": {"totalCount": 0},
                    },
                }
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_graphql_summary(["owner/alpha"])

        meta = await db.get_repo_metadata("owner/alpha")
        assert meta is not None
        assert meta["stars"] == 42
        assert meta["forks"] == 7

    async def test_stores_open_issues_and_releases(self, collector, db, httpx_mock):
        """open_issues_count and releases_count are stored from GraphQL data."""
        httpx_mock.add_response(
            url=GRAPHQL_URL,
            method="POST",
            json={
                "data": {
                    "repo0": {
                        "stargazerCount": 5,
                        "forkCount": 1,
                        "issues": {"totalCount": 8},
                        "pullRequests": {"totalCount": 2},
                        "releases": {"totalCount": 4},
                        "discussions": {"totalCount": 1},
                    },
                }
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_graphql_summary(["owner/alpha"])

        meta = await db.get_repo_metadata("owner/alpha")
        assert meta is not None
        assert meta["open_issues_count"] == 8
        assert meta["releases_count"] == 4

    async def test_handles_missing_repo_in_response(self, collector, db, httpx_mock):
        """A null repo entry in GraphQL data does not raise an error."""
        httpx_mock.add_response(
            url=GRAPHQL_URL,
            method="POST",
            json={
                "data": {
                    "repo0": None,
                    "repo1": {
                        "stargazerCount": 20,
                        "forkCount": 5,
                        "issues": {"totalCount": 0},
                        "pullRequests": {"totalCount": 0},
                        "releases": {"totalCount": 1},
                        "discussions": {"totalCount": 0},
                    },
                }
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )

        # Should not raise
        await collector.collect_graphql_summary(["owner/alpha", "owner/beta"])

        meta_alpha = await db.get_repo_metadata("owner/alpha")
        assert meta_alpha is None  # was None in response, not stored

        meta_beta = await db.get_repo_metadata("owner/beta")
        assert meta_beta is not None
        assert meta_beta["stars"] == 20

    async def test_empty_repo_list_makes_no_request(self, collector, db, httpx_mock):
        """Empty repo list skips the GraphQL call entirely."""
        await collector.collect_graphql_summary([])
        assert len(httpx_mock.get_requests()) == 0

    async def test_collect_all_calls_graphql_summary(self, db, httpx_mock):
        """collect_all() triggers collect_graphql_summary after the per-repo loop."""
        collector = GitHubCollector(
            token="test-token",
            db=db,
            repos=["owner/myrepo"],
        )

        # Traffic
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/traffic/views?per=day",
            json={"count": 0, "uniques": 0, "views": []},
            headers={"X-RateLimit-Remaining": "4999"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/traffic/clones?per=day",
            json={"count": 0, "uniques": 0, "clones": []},
            headers={"X-RateLimit-Remaining": "4998"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/traffic/popular/referrers",
            json=[],
            headers={"X-RateLimit-Remaining": "4997"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/traffic/popular/paths",
            json=[],
            headers={"X-RateLimit-Remaining": "4996"},
        )
        # People
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/stargazers",
            json=[],
            headers={"X-RateLimit-Remaining": "4995"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/subscribers",
            json=[],
            headers={"X-RateLimit-Remaining": "4994"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/forks?sort=newest",
            json=[],
            headers={"X-RateLimit-Remaining": "4993"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/stats/contributors",
            json=[],
            headers={"X-RateLimit-Remaining": "4992"},
        )
        # Issues
        for state in ("open", "closed"):
            httpx_mock.add_response(
                url=f"https://api.github.com/repos/owner/myrepo/issues?state={state}&per_page=30&sort=updated",
                json=[],
                headers={"X-RateLimit-Remaining": "4991"},
            )
        # Metadata
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo",
            json={
                "description": "", "language": "Python",
                "stargazers_count": 1, "forks_count": 0,
                "subscribers_count": 0, "open_issues_count": 0,
                "size": 10, "license": None, "topics": [],
                "created_at": "2024-01-01T00:00:00Z",
                "updated_at": "2026-01-01T00:00:00Z",
                "pushed_at": "2026-01-01T00:00:00Z",
                "default_branch": "main", "homepage": "",
            },
            headers={"X-RateLimit-Remaining": "4990"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/commits?per_page=1",
            json=[{}],
            headers={"X-RateLimit-Remaining": "4989"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/releases?per_page=1",
            json=[],
            headers={"X-RateLimit-Remaining": "4988"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/languages",
            json={"Python": 500},
            headers={"X-RateLimit-Remaining": "4987"},
        )
        # New per-repo endpoints
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/stats/commit_activity",
            json=[],
            headers={"X-RateLimit-Remaining": "4986"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/stats/code_frequency",
            json=[],
            headers={"X-RateLimit-Remaining": "4985"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/community/profile",
            json={"health_percentage": 80},
            headers={"X-RateLimit-Remaining": "4984"},
        )
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/myrepo/releases?per_page=100",
            json=[],
            headers={"X-RateLimit-Remaining": "4983"},
        )
        # Social mentions (3: HN, Reddit, Dev.to)
        httpx_mock.add_response(
            url="https://hn.algolia.com/api/v1/search?query=github.com/owner/myrepo&tags=story",
            json={"hits": []},
        )
        httpx_mock.add_response(
            url="https://www.reddit.com/search.json?q=github.com/owner/myrepo&sort=new&limit=10",
            json={"data": {"children": []}},
        )
        httpx_mock.add_response(
            url="https://dev.to/api/articles?tag=myrepo&per_page=5",
            json=[],
        )
        # Scorecard (1)
        httpx_mock.add_response(
            url="https://api.scorecard.dev/projects/github.com/owner/myrepo",
            json={"score": 8.0, "checks": []},
        )
        # Citations (2: Semantic Scholar, OpenAlex)
        httpx_mock.add_response(
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=github.com/owner/myrepo&limit=5"
                "&fields=title,authors,year,citationCount,externalIds"
            ),
            json={"data": []},
        )
        httpx_mock.add_response(
            url="https://api.openalex.org/works?search=github.com/owner/myrepo&per_page=5",
            json={"results": []},
        )
        # GraphQL summary (called last)
        httpx_mock.add_response(
            url=GRAPHQL_URL,
            method="POST",
            json={
                "data": {
                    "repo0": {
                        "stargazerCount": 99,
                        "forkCount": 9,
                        "issues": {"totalCount": 1},
                        "pullRequests": {"totalCount": 0},
                        "releases": {"totalCount": 2},
                        "discussions": {"totalCount": 0},
                    }
                }
            },
            headers={"X-RateLimit-Remaining": "4982"},
        )

        await collector.collect_all()

        # Verify GraphQL was called (last request should be to graphql endpoint)
        requests = httpx_mock.get_requests()
        graphql_requests = [r for r in requests if str(r.url) == GRAPHQL_URL]
        assert len(graphql_requests) == 1

        # Verify GraphQL data was stored
        meta = await db.get_repo_metadata("owner/myrepo")
        assert meta is not None
        assert meta["stars"] == 99
