"""Tests for social mention tracking (Issue #9).

Specs covered:
1. collect_social_mentions stores HN hits in DB
2. collect_social_mentions stores Reddit posts in DB
3. collect_social_mentions stores Dev.to articles in DB
4. Errors from external APIs are handled gracefully (best-effort)
5. GET /api/repos/{owner}/{repo}/mentions returns stored mentions
6. GET /api/mentions/recent returns recent mentions across all repos
7. Duplicate URLs are upserted, not duplicated
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_social.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def collector(db):
    return GitHubCollector(token="fake-token", db=db, repos=["owner/myrepo"])


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# --- Spec 1: HN collection ---


class TestHackerNewsCollection:
    async def test_stores_hn_hits(self, collector, db, httpx_mock):
        """Collector fetches HN search API and stores matching stories."""
        httpx_mock.add_response(
            url="https://hn.algolia.com/api/v1/search?query=github.com/owner/myrepo&tags=story",
            json={
                "hits": [
                    {
                        "title": "Show HN: myrepo – awesome tool",
                        "url": "https://github.com/owner/myrepo",
                        "points": 142,
                        "author": "hnuser1",
                    },
                    {
                        "title": "Using myrepo in production",
                        "url": "https://blog.example.com/myrepo",
                        "points": 55,
                        "author": "hnuser2",
                    },
                ]
            },
        )
        # Reddit and Dev.to return empty so they don't fail
        httpx_mock.add_response(
            url="https://www.reddit.com/search.json?q=github.com/owner/myrepo&sort=new&limit=10",
            json={"data": {"children": []}},
        )
        httpx_mock.add_response(
            url="https://dev.to/api/articles?tag=myrepo&per_page=5",
            json=[],
        )

        await collector.collect_social_mentions("owner/myrepo")

        mentions = await db.get_social_mentions("owner/myrepo")
        assert len(mentions) == 2
        hn_mentions = [m for m in mentions if m["platform"] == "hackernews"]
        assert len(hn_mentions) == 2
        urls = {m["url"] for m in hn_mentions}
        assert "https://github.com/owner/myrepo" in urls
        scores = {m["score"] for m in hn_mentions}
        assert 142 in scores

    async def test_hn_hit_without_url_is_skipped(self, collector, db, httpx_mock):
        """HN hits without a url field are skipped."""
        httpx_mock.add_response(
            url="https://hn.algolia.com/api/v1/search?query=github.com/owner/myrepo&tags=story",
            json={
                "hits": [
                    {"title": "No url here", "url": None, "points": 10, "author": "user"},
                ]
            },
        )
        httpx_mock.add_response(
            url="https://www.reddit.com/search.json?q=github.com/owner/myrepo&sort=new&limit=10",
            json={"data": {"children": []}},
        )
        httpx_mock.add_response(
            url="https://dev.to/api/articles?tag=myrepo&per_page=5",
            json=[],
        )

        await collector.collect_social_mentions("owner/myrepo")

        mentions = await db.get_social_mentions("owner/myrepo")
        assert len(mentions) == 0


# --- Spec 2: Reddit collection ---


class TestRedditCollection:
    async def test_stores_reddit_posts(self, collector, db, httpx_mock):
        """Collector fetches Reddit search and stores posts."""
        httpx_mock.add_response(
            url="https://hn.algolia.com/api/v1/search?query=github.com/owner/myrepo&tags=story",
            json={"hits": []},
        )
        httpx_mock.add_response(
            url="https://www.reddit.com/search.json?q=github.com/owner/myrepo&sort=new&limit=10",
            json={
                "data": {
                    "children": [
                        {
                            "data": {
                                "title": "Check out myrepo!",
                                "url": "https://github.com/owner/myrepo",
                                "score": 88,
                                "author": "redditor1",
                                "permalink": "/r/programming/comments/abc123/check_out_myrepo",
                            }
                        },
                    ]
                }
            },
        )
        httpx_mock.add_response(
            url="https://dev.to/api/articles?tag=myrepo&per_page=5",
            json=[],
        )

        await collector.collect_social_mentions("owner/myrepo")

        mentions = await db.get_social_mentions("owner/myrepo")
        reddit_mentions = [m for m in mentions if m["platform"] == "reddit"]
        assert len(reddit_mentions) == 1
        assert reddit_mentions[0]["title"] == "Check out myrepo!"
        assert reddit_mentions[0]["score"] == 88
        assert reddit_mentions[0]["author"] == "redditor1"
        # Should use reddit permalink URL
        assert "reddit.com" in reddit_mentions[0]["url"]


# --- Spec 3: Dev.to collection ---


class TestDevToCollection:
    async def test_stores_devto_articles(self, collector, db, httpx_mock):
        """Collector fetches Dev.to articles and stores them."""
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
            json=[
                {
                    "title": "Building with myrepo",
                    "url": "https://dev.to/devuser/building-with-myrepo-1234",
                    "positive_reactions_count": 22,
                    "user": {"username": "devuser"},
                },
            ],
        )

        await collector.collect_social_mentions("owner/myrepo")

        mentions = await db.get_social_mentions("owner/myrepo")
        devto_mentions = [m for m in mentions if m["platform"] == "devto"]
        assert len(devto_mentions) == 1
        assert devto_mentions[0]["title"] == "Building with myrepo"
        assert devto_mentions[0]["score"] == 22
        assert devto_mentions[0]["author"] == "devuser"


# --- Spec 4: Graceful error handling ---


class TestSocialMentionsErrorHandling:
    async def test_hn_error_does_not_abort_collection(self, collector, db, httpx_mock):
        """An HN API error is swallowed; Reddit and Dev.to still run."""
        httpx_mock.add_response(
            url="https://hn.algolia.com/api/v1/search?query=github.com/owner/myrepo&tags=story",
            status_code=500,
        )
        httpx_mock.add_response(
            url="https://www.reddit.com/search.json?q=github.com/owner/myrepo&sort=new&limit=10",
            json={"data": {"children": []}},
        )
        httpx_mock.add_response(
            url="https://dev.to/api/articles?tag=myrepo&per_page=5",
            json=[
                {
                    "title": "A Dev.to post",
                    "url": "https://dev.to/user/post-1",
                    "positive_reactions_count": 5,
                    "user": {"username": "user"},
                }
            ],
        )

        # Should not raise
        await collector.collect_social_mentions("owner/myrepo")

        mentions = await db.get_social_mentions("owner/myrepo")
        # Dev.to should still have been collected
        assert any(m["platform"] == "devto" for m in mentions)


# --- Spec 5 & 6: API endpoints ---


class TestSocialMentionsAPI:
    async def test_get_mentions_for_repo(self, client, db):
        """GET /api/repos/{owner}/{repo}/mentions returns that repo's mentions."""
        await db.upsert_social_mention(
            "owner/myrepo", "hackernews",
            "https://news.ycombinator.com/item?id=12345",
            title="My HN post", score=99, author="hnuser",
        )
        await db.upsert_social_mention(
            "owner/myrepo", "reddit",
            "https://www.reddit.com/r/python/comments/xyz",
            title="Reddit post", score=44, author="redditor",
        )

        resp = await client.get("/api/repos/owner/myrepo/mentions")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        platforms = {m["platform"] for m in data}
        assert "hackernews" in platforms
        assert "reddit" in platforms

    async def test_get_mentions_empty(self, client):
        """Returns empty list for repo with no mentions."""
        resp = await client.get("/api/repos/owner/norepo/mentions")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_recent_mentions_across_repos(self, client, db):
        """GET /api/mentions/recent returns mentions from all repos."""
        await db.upsert_social_mention(
            "owner/repo1", "hackernews",
            "https://hn.example.com/1",
            title="HN post 1", score=10, author="user1",
        )
        await db.upsert_social_mention(
            "owner/repo2", "devto",
            "https://dev.to/user/post-2",
            title="Dev.to post", score=5, author="user2",
        )

        resp = await client.get("/api/mentions/recent")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        repos = {m["repo_name"] for m in data}
        assert "owner/repo1" in repos
        assert "owner/repo2" in repos

    async def test_get_recent_mentions_limit(self, client, db):
        """GET /api/mentions/recent respects the limit query parameter."""
        for i in range(5):
            await db.upsert_social_mention(
                "owner/repo1", "hackernews",
                f"https://hn.example.com/{i}",
                title=f"Post {i}", score=i, author="user",
            )

        resp = await client.get("/api/mentions/recent?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3


# --- Spec 7: Duplicate upsert ---


class TestSocialMentionUpsert:
    async def test_duplicate_url_is_upserted_not_duplicated(self, db):
        """Inserting the same URL twice updates rather than creating duplicate."""
        url = "https://news.ycombinator.com/item?id=99999"
        await db.upsert_social_mention("owner/repo", "hackernews", url, score=10)
        await db.upsert_social_mention("owner/repo", "hackernews", url, score=200)

        mentions = await db.get_social_mentions("owner/repo")
        assert len(mentions) == 1
        assert mentions[0]["score"] == 200
