"""Tests for workflow runs / CI dashboard API.

Specs: Issue #29
1. GET /api/repos/{owner}/{repo}/workflow-runs returns workflow runs
2. Returns empty list for unknown repo
3. Results include workflow_name, status, conclusion, branch, duration
"""
import pytest
from httpx import ASGITransport, AsyncClient
from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_wf.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestWorkflowRunsEndpoint:
    async def test_returns_empty_for_unknown_repo(self, client):
        resp = await client.get("/api/repos/no/exist/workflow-runs")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_returns_stored_runs(self, client, db):
        await db._db.execute(
            """INSERT INTO workflow_runs
               (repo_name, run_id, workflow_name, status, conclusion,
                event, branch, created_at, run_started_at, updated_at, duration_seconds)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            ("a/b", 123, "CI", "completed", "success",
             "push", "main", "2026-03-20T10:00:00Z", "2026-03-20T10:00:01Z",
             "2026-03-20T10:02:00Z", 119)
        )
        await db._db.commit()
        resp = await client.get("/api/repos/a/b/workflow-runs")
        assert resp.status_code == 200
        runs = resp.json()
        assert len(runs) == 1
        assert runs[0]["workflow_name"] == "CI"
        assert runs[0]["conclusion"] == "success"
        assert runs[0]["duration_seconds"] == 119
