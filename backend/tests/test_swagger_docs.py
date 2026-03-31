"""Tests for Swagger UI / OpenAPI documentation endpoint.

Specs: Issue #23
1. GET /api/docs should return Swagger UI HTML
2. GET /openapi.json should return the OpenAPI spec
"""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_docs.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSwaggerDocs:
    async def test_docs_endpoint_returns_html(self, client):
        resp = await client.get("/api/docs")
        assert resp.status_code == 200
        assert "text/html" in resp.headers.get("content-type", "")

    async def test_openapi_json_returns_spec(self, client):
        resp = await client.get("/openapi.json")
        assert resp.status_code == 200
        data = resp.json()
        assert data["info"]["title"] == "gh-tracker"
        assert "paths" in data
        assert "/api/health" in data["paths"]
