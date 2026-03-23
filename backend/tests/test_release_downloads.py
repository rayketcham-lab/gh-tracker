"""Tests for release download tracking (Issue #13).

Specs:
1. collect_releases fetches /repos/{owner}/{repo}/releases
2. Iterates assets and stores download_count per asset
3. DB upsert and retrieval work correctly
4. API endpoint returns release assets
5. Empty/None responses handled gracefully
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_releases.db"))
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


SAMPLE_RELEASES = [
    {
        "tag_name": "v1.2.0",
        "assets": [
            {
                "name": "app-linux-amd64",
                "download_count": 1500,
                "size": 8_000_000,
                "created_at": "2026-01-15T10:00:00Z",
            },
            {
                "name": "app-darwin-arm64",
                "download_count": 800,
                "size": 7_500_000,
                "created_at": "2026-01-15T10:00:00Z",
            },
        ],
    },
    {
        "tag_name": "v1.1.0",
        "assets": [
            {
                "name": "app-linux-amd64",
                "download_count": 3000,
                "size": 7_800_000,
                "created_at": "2025-12-01T10:00:00Z",
            },
        ],
    },
]


class TestCollectReleases:
    async def test_stores_asset_download_counts(self, collector, db, httpx_mock):
        """collect_releases stores download_count for each asset."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=SAMPLE_RELEASES,
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_releases("owner/repo")

        assets = await db.get_release_assets("owner/repo")
        assert len(assets) == 3

    async def test_stores_correct_download_counts(self, collector, db, httpx_mock):
        """Each asset's download_count is correctly stored."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=[SAMPLE_RELEASES[0]],
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_releases("owner/repo")

        assets = await db.get_release_assets("owner/repo")
        download_counts = {a["asset_name"]: a["download_count"] for a in assets}
        assert download_counts["app-linux-amd64"] == 1500
        assert download_counts["app-darwin-arm64"] == 800

    async def test_stores_size_and_created_at(self, collector, db, httpx_mock):
        """Asset size and created_at are stored."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=[SAMPLE_RELEASES[0]],
            headers={"X-RateLimit-Remaining": "4990"},
        )

        await collector.collect_releases("owner/repo")

        assets = await db.get_release_assets("owner/repo")
        linux_asset = next(a for a in assets if a["asset_name"] == "app-linux-amd64")
        assert linux_asset["size_bytes"] == 8_000_000
        assert linux_asset["created_at"] == "2026-01-15T10:00:00Z"

    async def test_upsert_updates_download_count(self, collector, db, httpx_mock):
        """Re-collecting same asset updates download_count (upsert)."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=[{
                "tag_name": "v1.0.0",
                "assets": [{"name": "app.tar.gz", "download_count": 100,
                             "size": 1000, "created_at": "2025-01-01T00:00:00Z"}],
            }],
            headers={"X-RateLimit-Remaining": "4990"},
        )
        await collector.collect_releases("owner/repo")

        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=[{
                "tag_name": "v1.0.0",
                "assets": [{"name": "app.tar.gz", "download_count": 150,
                             "size": 1000, "created_at": "2025-01-01T00:00:00Z"}],
            }],
            headers={"X-RateLimit-Remaining": "4989"},
        )
        await collector.collect_releases("owner/repo")

        assets = await db.get_release_assets("owner/repo")
        assert len(assets) == 1
        assert assets[0]["download_count"] == 150

    async def test_none_response_skipped(self, collector, db, httpx_mock):
        """304 / None response does not raise."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            status_code=304,
            headers={"X-RateLimit-Remaining": "4990"},
        )
        await collector.collect_releases("owner/repo")
        assert await db.get_release_assets("owner/repo") == []

    async def test_release_without_tag_skipped(self, collector, db, httpx_mock):
        """Releases missing tag_name are skipped."""
        httpx_mock.add_response(
            url="https://api.github.com/repos/owner/repo/releases?per_page=100",
            json=[{"tag_name": "", "assets": [{"name": "x", "download_count": 5,
                                               "size": 10, "created_at": ""}]}],
            headers={"X-RateLimit-Remaining": "4990"},
        )
        await collector.collect_releases("owner/repo")
        assert await db.get_release_assets("owner/repo") == []


class TestReleaseAssetsDB:
    async def test_upsert_and_retrieve(self, db):
        await db.upsert_release_asset("owner/repo", "v1.0.0", "app.tar.gz",
                                      download_count=500, size_bytes=1024,
                                      created_at="2026-01-01T00:00:00Z")
        assets = await db.get_release_assets("owner/repo")
        assert len(assets) == 1
        assert assets[0]["release_tag"] == "v1.0.0"
        assert assets[0]["asset_name"] == "app.tar.gz"
        assert assets[0]["download_count"] == 500

    async def test_unique_constraint(self, db):
        """Same (repo, tag, asset) upserts update rather than duplicate."""
        await db.upsert_release_asset("owner/repo", "v1.0.0", "app.tar.gz",
                                      download_count=100)
        await db.upsert_release_asset("owner/repo", "v1.0.0", "app.tar.gz",
                                      download_count=200)
        assets = await db.get_release_assets("owner/repo")
        assert len(assets) == 1
        assert assets[0]["download_count"] == 200

    async def test_empty_returns_empty_list(self, db):
        assert await db.get_release_assets("nobody/nothing") == []


class TestReleasesAPIEndpoint:
    async def test_returns_empty_for_unknown_repo(self, client):
        resp = await client.get("/api/repos/nobody/nothing/releases")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_assets(self, client, db):
        await db.upsert_release_asset("owner/repo", "v1.0.0", "app-linux",
                                      download_count=999, size_bytes=5000,
                                      created_at="2026-01-01T00:00:00Z")
        await db.upsert_release_asset("owner/repo", "v1.0.0", "app-darwin",
                                      download_count=333, size_bytes=4800,
                                      created_at="2026-01-01T00:00:00Z")
        resp = await client.get("/api/repos/owner/repo/releases")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        names = {a["asset_name"] for a in data}
        assert "app-linux" in names
        assert "app-darwin" in names

    async def test_download_count_in_response(self, client, db):
        await db.upsert_release_asset("owner/repo", "v2.0.0", "binary",
                                      download_count=42)
        resp = await client.get("/api/repos/owner/repo/releases")
        data = resp.json()
        assert data[0]["download_count"] == 42
