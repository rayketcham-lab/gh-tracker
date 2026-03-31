"""Tests for security alerts dashboard API. Issue #32."""

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_security.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


class TestSecurityAlerts:
    async def test_get_alerts_empty(self, client):
        resp = await client.get("/api/repos/no/exist/security/alerts")
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_get_alerts_with_data(self, client, db):
        await db._db.execute(
            """INSERT INTO security_alerts
               (repo_name, alert_type, severity, state, package_name,
                description, url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("a/b", "dependabot", "high", "open", "lodash",
             "Prototype pollution", "https://github.com/a/b/sec/1", "2026-03-20")
        )
        await db._db.commit()
        resp = await client.get("/api/repos/a/b/security/alerts")
        assert resp.status_code == 200
        alerts = resp.json()
        assert len(alerts) == 1
        assert alerts[0]["severity"] == "high"
        assert alerts[0]["alert_type"] == "dependabot"

    async def test_filter_by_severity(self, client, db):
        for sev in ("critical", "high", "medium"):
            await db._db.execute(
                """INSERT INTO security_alerts
                   (repo_name, alert_type, severity, state, package_name,
                    description, url, created_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                ("a/b", "dependabot", sev, "open", "pkg",
                 f"{sev} alert", f"https://url/{sev}", "2026-03-20")
            )
        await db._db.commit()
        resp = await client.get("/api/repos/a/b/security/alerts?severity=critical")
        assert len(resp.json()) == 1

    async def test_security_summary(self, client, db):
        await db._db.execute(
            """INSERT INTO security_alerts
               (repo_name, alert_type, severity, state, package_name,
                description, url, created_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            ("a/b", "dependabot", "high", "open", "pkg",
             "desc", "https://url", "2026-03-20")
        )
        await db._db.commit()
        resp = await client.get("/api/security/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 1
        assert data[0]["repo_name"] == "a/b"
        assert data[0]["high"] == 1
