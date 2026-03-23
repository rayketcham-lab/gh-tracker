"""GitHub traffic data collector — archives metrics before the 14-day expiry."""

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx

from app.database import Database

logger = logging.getLogger(__name__)

GITHUB_API = "https://api.github.com"
RATE_LIMIT_FLOOR = 50  # Stop making requests below this threshold
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # seconds


class RateLimitError(Exception):
    """Raised when rate limit is too low to continue."""


class GitHubCollector:
    def __init__(self, token: str, db: Database, repos: list[str]) -> None:
        self.token = token
        self.db = db
        self.repos = repos
        self.rate_limit_remaining: int | None = None
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            self._client = httpx.AsyncClient(
                headers={
                    "Authorization": f"Bearer {self.token}",
                    "Accept": "application/vnd.github+json",
                    "X-GitHub-Api-Version": "2022-11-28",
                },
                timeout=30.0,
            )
        return self._client

    async def close(self) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _check_rate_limit(self) -> None:
        if self.rate_limit_remaining is not None and self.rate_limit_remaining < RATE_LIMIT_FLOOR:
            raise RateLimitError(
                f"Rate limit too low: {self.rate_limit_remaining} remaining "
                f"(floor: {RATE_LIMIT_FLOOR})"
            )

    def _update_rate_limit(self, response: httpx.Response) -> None:
        remaining = response.headers.get("X-RateLimit-Remaining")
        if remaining is not None:
            self.rate_limit_remaining = int(remaining)

    async def _request(self, url: str, etag_key: str | None = None) -> httpx.Response | None:
        """Make a request with ETag caching and 202 retry logic."""
        self._check_rate_limit()

        client = await self._get_client()
        headers = {}

        if etag_key:
            cached_etag = await self.db.get_etag(etag_key)
            if cached_etag:
                headers["If-None-Match"] = cached_etag

        for attempt in range(MAX_RETRIES):
            response = await client.get(url, headers=headers)
            self._update_rate_limit(response)

            if response.status_code == 304:
                return None  # Not modified, data is current

            if response.status_code == 202:
                if attempt < MAX_RETRIES - 1:
                    await asyncio.sleep(RETRY_DELAY * (attempt + 1))
                    continue
                return None  # Give up after retries

            response.raise_for_status()

            # Cache the ETag
            if etag_key and "ETag" in response.headers:
                await self.db.store_etag(etag_key, response.headers["ETag"])

            return response

        return None

    async def collect_views(self, repo: str) -> None:
        """Collect daily view counts for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/traffic/views?per=day"
        etag_key = f"{repo}/traffic/views"

        response = await self._request(url, etag_key)
        if response is None:
            return

        data = response.json()
        await self.db.store_raw_response(repo, "traffic/views", json.dumps(data))

        for entry in data.get("views", []):
            date = entry["timestamp"][:10]
            await self.db.upsert_daily_metrics(
                repo, date, views=entry["count"], unique_visitors=entry["uniques"]
            )

    async def collect_clones(self, repo: str) -> None:
        """Collect daily clone counts for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/traffic/clones?per=day"
        etag_key = f"{repo}/traffic/clones"

        response = await self._request(url, etag_key)
        if response is None:
            return

        data = response.json()
        await self.db.store_raw_response(repo, "traffic/clones", json.dumps(data))

        for entry in data.get("clones", []):
            date = entry["timestamp"][:10]
            await self.db.upsert_daily_metrics(
                repo, date, clones=entry["count"], unique_cloners=entry["uniques"]
            )

    async def collect_referrers(self, repo: str) -> None:
        """Collect top referral sources."""
        url = f"{GITHUB_API}/repos/{repo}/traffic/popular/referrers"

        response = await self._request(url)
        if response is None:
            return

        data = response.json()
        await self.db.store_raw_response(repo, "traffic/referrers", json.dumps(data))

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        await self.db.store_referrers(repo, today, data)

    async def collect_paths(self, repo: str) -> None:
        """Collect most-viewed content pages."""
        url = f"{GITHUB_API}/repos/{repo}/traffic/popular/paths"

        response = await self._request(url)
        if response is None:
            return

        data = response.json()
        await self.db.store_raw_response(repo, "traffic/paths", json.dumps(data))

        today = datetime.now(UTC).strftime("%Y-%m-%d")
        await self.db.store_paths(repo, today, data)

    async def collect_all(self) -> None:
        """Collect all traffic data for all configured repositories."""
        for repo in self.repos:
            try:
                await self.collect_views(repo)
                await self.collect_clones(repo)
                await self.collect_referrers(repo)
                await self.collect_paths(repo)
            except RateLimitError:
                logger.warning("Rate limit reached, stopping collection")
                break
            except Exception:
                logger.exception("Error collecting data for %s", repo)
                continue
