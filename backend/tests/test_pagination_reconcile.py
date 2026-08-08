"""Tests for issue #37 — list endpoints must paginate, and must reconcile.

Two defects, one root cause. The collectors fetched a single page (GitHub
defaults to 30 items) and only ever INSERTed:

1. Truncation. Any repo with more than 30 stargazers, watchers, forkers or
   issues silently lost everyone past the first page.
2. Staleness. Nobody was ever removed, so anyone who unstarred, unwatched or
   deleted their fork lingered forever and inflated every derived count.

The second bug also corrupted watcher history: detect_watcher_changes diffed
the stored watchers against a single page, so on a repo with more than 30
watchers it recorded everyone past page one as "removed" on *every* run.
"""

import pytest

from app.collector import GitHubCollector, _next_page_url
from app.database import Database

API = "https://api.github.com"


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_paginate.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
def collector(db):
    return GitHubCollector(token="test-token-fake", db=db, repos=["owner/repo"])


def _link(url: str, rel: str = "next") -> str:
    return f'<{url}>; rel="{rel}"'


# --- Link header parsing ---------------------------------------------------


class TestNextPageUrl:
    def test_returns_none_for_empty_header(self):
        assert _next_page_url("") is None

    def test_returns_none_when_only_prev_and_last(self):
        header = f'{_link("https://x/1", "prev")}, {_link("https://x/9", "last")}'
        assert _next_page_url(header) is None

    def test_extracts_next_url(self):
        header = f'{_link("https://x/2")}, {_link("https://x/9", "last")}'
        assert _next_page_url(header) == "https://x/2"

    def test_extracts_next_when_not_first_in_header(self):
        header = f'{_link("https://x/1", "prev")}, {_link("https://x/3")}'
        assert _next_page_url(header) == "https://x/3"


# --- Pagination ------------------------------------------------------------


class TestPaginationNotTruncated:
    async def test_stargazers_beyond_thirty_are_all_stored(self, collector, db, httpx_mock):
        """A repo with 45 stargazers must yield 45 rows, not 30."""
        page1 = [
            {"user": {"login": f"user{i}"}, "starred_at": "2026-01-01T00:00:00Z"}
            for i in range(30)
        ]
        page2 = [
            {"user": {"login": f"user{i}"}, "starred_at": "2026-01-02T00:00:00Z"}
            for i in range(30, 45)
        ]
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/stargazers?per_page=100",
            json=page1,
            headers={"Link": _link(f"{API}/repos/owner/repo/stargazers?per_page=100&page=2")},
        )
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/stargazers?per_page=100&page=2",
            json=page2,
        )

        await collector.collect_stargazers("owner/repo")

        stored = await db.get_stargazers("owner/repo")
        assert len(stored) == 45
        assert {s["username"] for s in stored} == {f"user{i}" for i in range(45)}

    async def test_watchers_beyond_thirty_are_all_stored(self, collector, db, httpx_mock):
        page1 = [{"login": f"w{i}"} for i in range(30)]
        page2 = [{"login": f"w{i}"} for i in range(30, 40)]
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100",
            json=page1,
            headers={"Link": _link(f"{API}/repos/owner/repo/subscribers?per_page=100&page=2")},
        )
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100&page=2",
            json=page2,
        )

        await collector.collect_watchers("owner/repo")

        assert len(await db.get_watchers("owner/repo")) == 40

    async def test_requests_the_maximum_page_size(self, collector, db, httpx_mock):
        """per_page=100 keeps the request count down on large repos."""
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100", json=[]
        )
        await collector.collect_watchers("owner/repo")
        assert "per_page=100" in str(httpx_mock.get_requests()[0].url)


# --- Reconciliation --------------------------------------------------------


class TestReconciliation:
    async def test_unstarred_user_is_removed(self, collector, db, httpx_mock):
        """The bug that made the dashboard report 7 stars against GitHub's 4."""
        await db.upsert_stargazer("owner/repo", "leaver", "2026-01-01T00:00:00Z")
        await db.upsert_stargazer("owner/repo", "stayer", "2026-01-01T00:00:00Z")

        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/stargazers?per_page=100",
            json=[{"user": {"login": "stayer"}, "starred_at": "2026-01-01T00:00:00Z"}],
        )

        await collector.collect_stargazers("owner/repo")

        assert {s["username"] for s in await db.get_stargazers("owner/repo")} == {"stayer"}

    async def test_deleted_fork_is_removed(self, collector, db, httpx_mock):
        await db.upsert_forker("owner/repo", "gone", "gone/repo", "2026-01-01T00:00:00Z")
        await db.upsert_forker("owner/repo", "kept", "kept/repo", "2026-01-01T00:00:00Z")

        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/forks?sort=newest&per_page=100",
            json=[{
                "owner": {"login": "kept"},
                "full_name": "kept/repo",
                "created_at": "2026-01-01T00:00:00Z",
            }],
        )

        await collector.collect_forkers("owner/repo")

        assert {f["username"] for f in await db.get_forkers("owner/repo")} == {"kept"}

    async def test_empty_upstream_clears_the_repo(self, db):
        """Zero members is a real state, not a fetch failure."""
        await db.upsert_watcher("owner/repo", "someone")
        removed = await db.reconcile_watchers("owner/repo", [])
        assert removed == 1
        assert await db.get_watchers("owner/repo") == []

    async def test_other_repos_are_untouched(self, db):
        await db.upsert_stargazer("owner/repo", "alice", "")
        await db.upsert_stargazer("other/repo", "alice", "")

        await db.reconcile_stargazers("owner/repo", [])

        assert await db.get_stargazers("owner/repo") == []
        assert len(await db.get_stargazers("other/repo")) == 1

    async def test_failed_fetch_does_not_delete_anything(self, collector, db, httpx_mock):
        """A partial or failed fetch must never be treated as ground truth."""
        await db.upsert_stargazer("owner/repo", "alice", "")
        await db.upsert_stargazer("owner/repo", "bob", "")

        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/stargazers?per_page=100", status_code=500
        )

        with pytest.raises(Exception):
            await collector.collect_stargazers("owner/repo")

        assert len(await db.get_stargazers("owner/repo")) == 2

    async def test_refuses_unknown_table(self, db):
        with pytest.raises(ValueError, match="unknown table"):
            await db._reconcile_usernames("repo_metadata", "owner/repo", [])


# --- Watcher-change fabrication --------------------------------------------


class TestWatcherChangesNotFabricated:
    async def test_no_removals_when_watchers_span_two_pages(
        self, collector, db, httpx_mock
    ):
        """35 unchanged watchers must produce zero 'removed' events."""
        watchers = [f"w{i}" for i in range(35)]
        for name in watchers:
            await db.upsert_watcher("owner/repo", name)

        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100",
            json=[{"login": n} for n in watchers[:30]],
            headers={"Link": _link(f"{API}/repos/owner/repo/subscribers?per_page=100&page=2")},
        )
        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100&page=2",
            json=[{"login": n} for n in watchers[30:]],
        )

        await collector.detect_watcher_changes("owner/repo")

        changes = await db.get_watcher_changes("owner/repo")
        assert [c for c in changes if c["action"] == "removed"] == []

    async def test_genuine_removal_is_still_recorded(self, collector, db, httpx_mock):
        await db.upsert_watcher("owner/repo", "stayer")
        await db.upsert_watcher("owner/repo", "leaver")

        httpx_mock.add_response(
            url=f"{API}/repos/owner/repo/subscribers?per_page=100",
            json=[{"login": "stayer"}],
        )

        await collector.detect_watcher_changes("owner/repo")

        removed = [
            c for c in await db.get_watcher_changes("owner/repo")
            if c["action"] == "removed"
        ]
        assert [c["username"] for c in removed] == ["leaver"]
