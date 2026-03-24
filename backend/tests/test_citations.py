"""Tests for academic citation tracking (Issue #19).

Specs covered:
1. collect_citations stores Semantic Scholar papers in DB
2. collect_citations stores OpenAlex works in DB
3. Errors from external APIs are handled gracefully
4. GET /api/repos/{owner}/{repo}/citations returns stored citations
5. GET /api/citations/summary returns aggregated citation counts
6. Duplicate URLs are upserted, not duplicated
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.collector import GitHubCollector
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_citations.db"))
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


# --- Spec 1: Semantic Scholar ---


class TestSemanticScholarCollection:
    async def test_stores_semantic_scholar_papers(self, collector, db, httpx_mock):
        """Collector fetches Semantic Scholar and stores papers in citations table."""
        httpx_mock.add_response(
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=github.com/owner/myrepo&limit=5"
                "&fields=title,authors,year,citationCount,externalIds"
            ),
            json={
                "data": [
                    {
                        "paperId": "abc123",
                        "title": "Deep Learning with myrepo",
                        "authors": [
                            {"name": "Alice Smith"},
                            {"name": "Bob Jones"},
                        ],
                        "year": 2024,
                        "citationCount": 42,
                    },
                ]
            },
        )
        # OpenAlex returns empty
        httpx_mock.add_response(
            url="https://api.openalex.org/works?search=github.com/owner/myrepo&per_page=5",
            json={"results": []},
        )

        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert len(citations) == 1
        c = citations[0]
        assert c["source"] == "semantic_scholar"
        assert c["title"] == "Deep Learning with myrepo"
        assert "Alice Smith" in c["authors"]
        assert "Bob Jones" in c["authors"]
        assert c["year"] == 2024
        assert c["citation_count"] == 42
        assert "semanticscholar.org" in c["url"]

    async def test_paper_without_id_is_skipped(self, collector, db, httpx_mock):
        """A Semantic Scholar paper with no paperId is skipped."""
        httpx_mock.add_response(
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=github.com/owner/myrepo&limit=5"
                "&fields=title,authors,year,citationCount,externalIds"
            ),
            json={
                "data": [
                    {
                        "paperId": None,
                        "title": "Paper with no ID",
                        "authors": [],
                        "year": 2023,
                        "citationCount": 5,
                    },
                ]
            },
        )
        httpx_mock.add_response(
            url="https://api.openalex.org/works?search=github.com/owner/myrepo&per_page=5",
            json={"results": []},
        )

        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert len(citations) == 0


# --- Spec 2: OpenAlex ---


class TestOpenAlexCollection:
    async def test_stores_openalex_works(self, collector, db, httpx_mock):
        """Collector fetches OpenAlex and stores works in citations table."""
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
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W12345",
                        "title": "Machine learning pipeline using myrepo",
                        "authorships": [
                            {"author": {"display_name": "Carol White"}},
                            {"author": {"display_name": "Dan Brown"}},
                        ],
                        "publication_year": 2025,
                        "cited_by_count": 17,
                    },
                ]
            },
        )

        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert len(citations) == 1
        c = citations[0]
        assert c["source"] == "openalex"
        assert c["title"] == "Machine learning pipeline using myrepo"
        assert "Carol White" in c["authors"]
        assert c["year"] == 2025
        assert c["citation_count"] == 17
        assert c["url"] == "https://openalex.org/W12345"

    async def test_work_without_id_is_skipped(self, collector, db, httpx_mock):
        """An OpenAlex work with no id is skipped."""
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
            json={
                "results": [
                    {
                        "id": None,
                        "title": "Work without ID",
                        "authorships": [],
                        "publication_year": 2024,
                        "cited_by_count": 3,
                    },
                ]
            },
        )

        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert len(citations) == 0


# --- Spec 3: Graceful error handling ---


class TestCitationErrorHandling:
    async def test_semantic_scholar_error_does_not_abort(self, collector, db, httpx_mock):
        """An error from Semantic Scholar is swallowed; OpenAlex still runs."""
        httpx_mock.add_response(
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=github.com/owner/myrepo&limit=5"
                "&fields=title,authors,year,citationCount,externalIds"
            ),
            status_code=429,  # Rate limited
        )
        httpx_mock.add_response(
            url="https://api.openalex.org/works?search=github.com/owner/myrepo&per_page=5",
            json={
                "results": [
                    {
                        "id": "https://openalex.org/W99",
                        "title": "Fallback OpenAlex paper",
                        "authorships": [],
                        "publication_year": 2024,
                        "cited_by_count": 2,
                    },
                ]
            },
        )

        # Should not raise
        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert any(c["source"] == "openalex" for c in citations)

    async def test_openalex_error_does_not_abort(self, collector, db, httpx_mock):
        """An error from OpenAlex is swallowed after Semantic Scholar succeeds."""
        httpx_mock.add_response(
            url=(
                "https://api.semanticscholar.org/graph/v1/paper/search"
                "?query=github.com/owner/myrepo&limit=5"
                "&fields=title,authors,year,citationCount,externalIds"
            ),
            json={
                "data": [
                    {
                        "paperId": "ss-paper-1",
                        "title": "SS Paper",
                        "authors": [],
                        "year": 2023,
                        "citationCount": 5,
                    }
                ]
            },
        )
        httpx_mock.add_response(
            url="https://api.openalex.org/works?search=github.com/owner/myrepo&per_page=5",
            status_code=503,
        )

        # Should not raise
        await collector.collect_citations("owner/myrepo")

        citations = await db.get_citations("owner/myrepo")
        assert any(c["source"] == "semantic_scholar" for c in citations)


# --- Spec 4 & 5: API endpoints ---


class TestCitationsAPI:
    async def test_get_citations_for_repo(self, client, db):
        """GET /api/repos/{owner}/{repo}/citations returns that repo's citations."""
        await db.upsert_citation(
            "owner/myrepo", "semantic_scholar",
            "https://www.semanticscholar.org/paper/paper1",
            title="Paper One", authors="Author A", year=2023, citation_count=50,
        )
        await db.upsert_citation(
            "owner/myrepo", "openalex",
            "https://openalex.org/W1",
            title="Work One", authors="Author B", year=2024, citation_count=15,
        )

        resp = await client.get("/api/repos/owner/myrepo/citations")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2
        # Should be ordered by citation_count desc
        assert data[0]["citation_count"] >= data[1]["citation_count"]

    async def test_get_citations_empty(self, client):
        """Returns empty list for repo with no citations."""
        resp = await client.get("/api/repos/owner/norepo/citations")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_citations_summary(self, client, db):
        """GET /api/citations/summary returns aggregated data per repo."""
        await db.upsert_citation(
            "owner/repo1", "semantic_scholar",
            "https://www.semanticscholar.org/paper/p1",
            title="Paper 1", authors="A", year=2022, citation_count=100,
        )
        await db.upsert_citation(
            "owner/repo1", "openalex",
            "https://openalex.org/W1",
            title="Work 1", authors="B", year=2023, citation_count=50,
        )
        await db.upsert_citation(
            "owner/repo2", "semantic_scholar",
            "https://www.semanticscholar.org/paper/p2",
            title="Paper 2", authors="C", year=2024, citation_count=200,
        )

        resp = await client.get("/api/citations/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

        # Find repo1 entry
        repo1 = next((r for r in data if r["repo_name"] == "owner/repo1"), None)
        assert repo1 is not None
        assert repo1["total_papers"] == 2
        assert repo1["total_citations"] == 150
        assert repo1["max_citations"] == 100

        # Find repo2 entry
        repo2 = next((r for r in data if r["repo_name"] == "owner/repo2"), None)
        assert repo2 is not None
        assert repo2["total_papers"] == 1
        assert repo2["total_citations"] == 200

    async def test_citations_summary_empty(self, client):
        """GET /api/citations/summary returns empty list when no data."""
        resp = await client.get("/api/citations/summary")
        assert resp.status_code == 200
        assert resp.json() == []


# --- Spec 6: Duplicate upsert ---


class TestCitationUpsert:
    async def test_duplicate_url_is_upserted_not_duplicated(self, db):
        """Inserting the same URL twice updates rather than creating a duplicate."""
        url = "https://www.semanticscholar.org/paper/paper-unique"
        await db.upsert_citation(
            "owner/repo", "semantic_scholar", url, citation_count=10
        )
        await db.upsert_citation(
            "owner/repo", "semantic_scholar", url, citation_count=999
        )

        citations = await db.get_citations("owner/repo")
        assert len(citations) == 1
        assert citations[0]["citation_count"] == 999
