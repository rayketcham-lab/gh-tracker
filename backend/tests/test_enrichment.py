"""Tests for third-party enrichment (Issue #8).

Specs covered:
1. collect_scorecard stores score and JSON in repo_metadata
2. collect_libraries_io stores dependent_repos_count and source_rank
3. collect_libraries_io is skipped when LIBRARIES_IO_KEY is not set
4. Errors from external APIs are handled gracefully
5. GET /api/repos/{owner}/{repo}/enrichment returns enrichment data
6. GET /api/repos/{owner}/{repo}/enrichment returns defaults when repo not in DB
"""

import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_enrichment.db"))
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


# --- Spec 1: Scorecard collection ---


class TestScorecardCollection:
    async def test_stores_scorecard_score(self, collector, db, httpx_mock):
        """Collector fetches OpenSSF Scorecard and stores score + JSON."""
        scorecard_payload = {
            "score": 7.5,
            "checks": [
                {"name": "Code-Review", "score": 10},
                {"name": "Maintained", "score": 10},
                {"name": "Vulnerabilities", "score": 10},
                {"name": "License", "score": 9},
            ],
        }
        httpx_mock.add_response(
            url="https://api.scorecard.dev/projects/github.com/owner/myrepo",
            json=scorecard_payload,
        )

        await collector.collect_scorecard("owner/myrepo")

        meta = await db.get_repo_metadata("owner/myrepo")
        assert meta is not None
        assert meta["scorecard_score"] == 7.5
        parsed = json.loads(meta["scorecard_json"])
        assert parsed["score"] == 7.5
        assert len(parsed["checks"]) == 4

    async def test_scorecard_error_is_handled_gracefully(self, collector, db, httpx_mock):
        """An error from the Scorecard API is swallowed."""
        httpx_mock.add_response(
            url="https://api.scorecard.dev/projects/github.com/owner/myrepo",
            status_code=404,
        )

        # Should not raise
        await collector.collect_scorecard("owner/myrepo")

        # Metadata may not exist at all, which is fine
        meta = await db.get_repo_metadata("owner/myrepo")
        # If metadata exists, scorecard_score should still be default -1
        if meta is not None:
            assert meta.get("scorecard_score", -1) == -1

    async def test_scorecard_skips_invalid_repo_name(self, collector, db, httpx_mock):
        """Repos without owner/name format are skipped without API call."""
        # No httpx mock registered — would fail if a request is made
        await collector.collect_scorecard("invalidrepo")
        # No error raised, no requests made


# --- Spec 2: Libraries.io collection ---


class TestLibrariesIoCollection:
    async def test_stores_libraries_io_data(self, collector, db, httpx_mock, monkeypatch):
        """Collector fetches Libraries.io and stores dependent_repos_count and source_rank."""
        monkeypatch.setenv("LIBRARIES_IO_KEY", "test-api-key")

        httpx_mock.add_response(
            url="https://libraries.io/api/github/owner/myrepo?api_key=test-api-key",
            json={
                "dependent_repos_count": 1234,
                "rank": 89,
                "name": "myrepo",
            },
        )

        await collector.collect_libraries_io("owner/myrepo")

        meta = await db.get_repo_metadata("owner/myrepo")
        assert meta is not None
        assert meta["dependent_repos_count"] == 1234
        assert meta["source_rank"] == 89

    async def test_libraries_io_skipped_without_key(self, collector, db, httpx_mock, monkeypatch):
        """Libraries.io collection is skipped if LIBRARIES_IO_KEY is not set."""
        monkeypatch.delenv("LIBRARIES_IO_KEY", raising=False)

        # No mock registered — would fail if a request is made
        await collector.collect_libraries_io("owner/myrepo")

        # Should complete without making any HTTP requests
        meta = await db.get_repo_metadata("owner/myrepo")
        assert meta is None  # Nothing was stored

    async def test_libraries_io_error_is_handled_gracefully(
        self, collector, db, httpx_mock, monkeypatch
    ):
        """An error from Libraries.io is swallowed."""
        monkeypatch.setenv("LIBRARIES_IO_KEY", "test-api-key")

        httpx_mock.add_response(
            url="https://libraries.io/api/github/owner/myrepo?api_key=test-api-key",
            status_code=500,
        )

        # Should not raise
        await collector.collect_libraries_io("owner/myrepo")


# --- Spec 3: DB column defaults ---


class TestEnrichmentDBDefaults:
    async def test_new_metadata_has_enrichment_defaults(self, db):
        """A freshly inserted repo metadata row has expected enrichment defaults."""
        await db.upsert_repo_metadata("owner/repo", stars=10)
        meta = await db.get_repo_metadata("owner/repo")
        assert meta is not None
        assert meta["scorecard_score"] == -1
        assert meta["scorecard_json"] == "{}"
        assert meta["dependent_repos_count"] == 0
        assert meta["source_rank"] == 0

    async def test_enrichment_columns_can_be_upserted(self, db):
        """scorecard_score, scorecard_json, dependent_repos_count, source_rank are writable."""
        await db.upsert_repo_metadata(
            "owner/repo",
            scorecard_score=8.2,
            scorecard_json='{"score": 8.2}',
            dependent_repos_count=500,
            source_rank=42,
        )
        meta = await db.get_repo_metadata("owner/repo")
        assert meta["scorecard_score"] == 8.2
        assert meta["scorecard_json"] == '{"score": 8.2}'
        assert meta["dependent_repos_count"] == 500
        assert meta["source_rank"] == 42


# --- Spec 5 & 6: API endpoint ---


class TestEnrichmentAPI:
    async def test_enrichment_endpoint_returns_data(self, client, db):
        """GET /api/repos/{owner}/{repo}/enrichment returns enrichment fields."""
        await db.upsert_repo_metadata(
            "owner/myrepo",
            scorecard_score=6.8,
            scorecard_json='{"score": 6.8}',
            dependent_repos_count=200,
            source_rank=55,
        )

        resp = await client.get("/api/repos/owner/myrepo/enrichment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_name"] == "owner/myrepo"
        assert data["scorecard_score"] == 6.8
        assert data["scorecard_json"] == '{"score": 6.8}'
        assert data["dependent_repos_count"] == 200
        assert data["source_rank"] == 55

    async def test_enrichment_endpoint_defaults_for_missing_repo(self, client):
        """GET /api/repos/{owner}/{repo}/enrichment returns defaults if repo not in DB."""
        resp = await client.get("/api/repos/owner/notexist/enrichment")
        assert resp.status_code == 200
        data = resp.json()
        assert data["repo_name"] == "owner/notexist"
        assert data["scorecard_score"] == -1
        assert data["scorecard_json"] == "{}"
        assert data["dependent_repos_count"] == 0
        assert data["source_rank"] == 0
