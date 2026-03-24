"""Tests for the GitHub webhook handler (Issue #3).

Specs covered:
1. HMAC-SHA256 signature verification (valid, invalid, missing)
2. Star event creates stargazer on 'created', deletes on 'deleted'
3. Fork event creates forker
4. Issues/pull_request event upserts issue
5. Duplicate delivery_id is silently ignored
6. GET /api/webhooks/events lists recent events
"""

import hashlib
import hmac
import json

import pytest
from httpx import ASGITransport, AsyncClient

from app.database import Database
from app.main import create_app

WEBHOOK_URL = "/api/webhooks/github"
EVENTS_URL = "/api/webhooks/events"


def _sign(body: bytes, secret: str) -> str:
    """Compute X-Hub-Signature-256 header value."""
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.fixture
async def db(tmp_path):
    database = Database(str(tmp_path / "test_webhook.db"))
    await database.initialize()
    yield database
    await database.close()


@pytest.fixture
async def client(db):
    app = create_app(db=db)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_payload(**kwargs) -> dict:
    base = {
        "action": "created",
        "repository": {"full_name": "owner/repo"},
        "sender": {"login": "alice"},
    }
    base.update(kwargs)
    return base


async def _post_webhook(
    client,
    event_type: str,
    payload: dict,
    delivery_id: str = "delivery-001",
    secret: str | None = None,
    signature: str | None = None,
) -> object:
    body = json.dumps(payload).encode()
    headers = {
        "X-GitHub-Event": event_type,
        "X-GitHub-Delivery": delivery_id,
        "Content-Type": "application/json",
    }
    if secret is not None:
        headers["X-Hub-Signature-256"] = _sign(body, secret)
    if signature is not None:
        headers["X-Hub-Signature-256"] = signature
    return await client.post(WEBHOOK_URL, content=body, headers=headers)


# ---------------------------------------------------------------------------
# Signature verification
# ---------------------------------------------------------------------------


class TestSignatureVerification:
    async def test_valid_signature_accepted(self, client, monkeypatch):
        monkeypatch.setenv("GH_WEBHOOK_SECRET", "mysecret")
        payload = _make_payload()
        resp = await _post_webhook(
            client, "ping", payload, secret="mysecret"
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    async def test_invalid_signature_rejected(self, client, monkeypatch):
        monkeypatch.setenv("GH_WEBHOOK_SECRET", "mysecret")
        payload = _make_payload()
        resp = await _post_webhook(
            client, "ping", payload, signature="sha256=deadbeef"
        )
        assert resp.status_code == 401

    async def test_missing_signature_rejected_when_secret_configured(
        self, client, monkeypatch
    ):
        monkeypatch.setenv("GH_WEBHOOK_SECRET", "mysecret")
        payload = _make_payload()
        body = json.dumps(payload).encode()
        headers = {
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "delivery-001",
            "Content-Type": "application/json",
        }
        resp = await client.post(WEBHOOK_URL, content=body, headers=headers)
        assert resp.status_code == 401

    async def test_no_secret_configured_accepts_all(self, client, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = _make_payload()
        body = json.dumps(payload).encode()
        headers = {
            "X-GitHub-Event": "ping",
            "X-GitHub-Delivery": "delivery-001",
            "Content-Type": "application/json",
        }
        resp = await client.post(WEBHOOK_URL, content=body, headers=headers)
        assert resp.status_code == 200


# ---------------------------------------------------------------------------
# Star events
# ---------------------------------------------------------------------------


class TestStarEvent:
    async def test_star_created_upserts_stargazer(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = {
            "action": "created",
            "starred_at": "2026-03-24T12:00:00Z",
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "alice"},
        }
        resp = await _post_webhook(client, "star", payload)
        assert resp.status_code == 200

        stargazers = await db.get_stargazers("owner/repo")
        usernames = [s["username"] for s in stargazers]
        assert "alice" in usernames

    async def test_star_deleted_removes_stargazer(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        # Pre-seed stargazer
        await db.upsert_stargazer("owner/repo", "alice", "2026-03-20T00:00:00Z")

        payload = {
            "action": "deleted",
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "alice"},
        }
        resp = await _post_webhook(client, "star", payload, delivery_id="del-001")
        assert resp.status_code == 200

        stargazers = await db.get_stargazers("owner/repo")
        usernames = [s["username"] for s in stargazers]
        assert "alice" not in usernames


# ---------------------------------------------------------------------------
# Fork events
# ---------------------------------------------------------------------------


class TestForkEvent:
    async def test_fork_creates_forker(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = {
            "action": "created",
            "forkee": {
                "full_name": "alice/repo",
                "created_at": "2026-03-24T10:00:00Z",
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "alice"},
        }
        resp = await _post_webhook(client, "fork", payload)
        assert resp.status_code == 200

        forkers = await db.get_forkers("owner/repo")
        usernames = [f["username"] for f in forkers]
        assert "alice" in usernames


# ---------------------------------------------------------------------------
# Issues / pull_request events
# ---------------------------------------------------------------------------


class TestIssueEvent:
    async def test_issue_event_upserts_issue(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Bug report",
                "state": "open",
                "user": {"login": "bob"},
                "labels": [{"name": "bug"}],
                "created_at": "2026-03-24T09:00:00Z",
                "closed_at": None,
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "bob"},
        }
        resp = await _post_webhook(client, "issues", payload)
        assert resp.status_code == 200

        issues = await db.get_issues("owner/repo")
        numbers = [i["number"] for i in issues]
        assert 42 in numbers

    async def test_pull_request_event_upserts_as_pr(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = {
            "action": "opened",
            "pull_request": {
                "number": 7,
                "title": "Add feature",
                "state": "open",
                "user": {"login": "carol"},
                "labels": [],
                "created_at": "2026-03-24T11:00:00Z",
                "closed_at": None,
            },
            "repository": {"full_name": "owner/repo"},
            "sender": {"login": "carol"},
        }
        resp = await _post_webhook(client, "pull_request", payload)
        assert resp.status_code == 200

        issues = await db.get_issues("owner/repo", is_pr=True)
        numbers = [i["number"] for i in issues]
        assert 7 in numbers


# ---------------------------------------------------------------------------
# Deduplication
# ---------------------------------------------------------------------------


class TestDeduplication:
    async def test_duplicate_delivery_id_ignored(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)
        payload = _make_payload()

        resp1 = await _post_webhook(
            client, "ping", payload, delivery_id="same-delivery"
        )
        resp2 = await _post_webhook(
            client, "ping", payload, delivery_id="same-delivery"
        )
        assert resp1.status_code == 200
        assert resp2.status_code == 200

        # Only one event should be stored
        events = await db.get_recent_webhook_events()
        same = [e for e in events if e["delivery_id"] == "same-delivery"]
        assert len(same) == 1


# ---------------------------------------------------------------------------
# Events list endpoint
# ---------------------------------------------------------------------------


class TestEventsListEndpoint:
    async def test_events_list_returns_recent(self, client, db, monkeypatch):
        monkeypatch.delenv("GH_WEBHOOK_SECRET", raising=False)

        for i in range(3):
            payload = _make_payload()
            await _post_webhook(
                client, "ping", payload, delivery_id=f"list-del-{i}"
            )

        resp = await client.get(EVENTS_URL)
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) >= 3
        # Each entry has expected keys
        assert "event_type" in data[0]
        assert "delivery_id" in data[0]

    async def test_events_list_empty_initially(self, client):
        resp = await client.get(EVENTS_URL)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)
