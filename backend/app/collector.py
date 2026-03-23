"""GitHub traffic data collector — archives metrics before the 14-day expiry."""

import asyncio
import json
import logging
from datetime import UTC, datetime

import httpx

from app.database import Database

GITHUB_GRAPHQL = "https://api.github.com/graphql"

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

    async def collect_stargazers(self, repo: str) -> None:
        """Collect stargazers with timestamps."""
        url = f"{GITHUB_API}/repos/{repo}/stargazers"
        self._check_rate_limit()
        client = await self._get_client()
        # Need star+json accept header for timestamps
        response = await client.get(
            url,
            headers={"Accept": "application/vnd.github.star+json"},
        )
        self._update_rate_limit(response)
        response.raise_for_status()

        for star in response.json():
            user = star.get("user", {})
            username = user.get("login", "")
            starred_at = star.get("starred_at", "")
            if username:
                await self.db.upsert_stargazer(repo, username, starred_at)

    async def collect_watchers(self, repo: str) -> None:
        """Collect watchers (subscribers)."""
        url = f"{GITHUB_API}/repos/{repo}/subscribers"
        response = await self._request(url)
        if response is None:
            return
        for user in response.json():
            username = user.get("login", "")
            if username:
                await self.db.upsert_watcher(repo, username)

    async def collect_forkers(self, repo: str) -> None:
        """Collect forks with owner info."""
        url = f"{GITHUB_API}/repos/{repo}/forks?sort=newest"
        response = await self._request(url)
        if response is None:
            return
        for fork in response.json():
            owner = fork.get("owner", {})
            username = owner.get("login", "")
            fork_name = fork.get("full_name", "")
            forked_at = fork.get("created_at", "")
            if username:
                await self.db.upsert_forker(repo, username, fork_name, forked_at)

    async def collect_contributors(self, repo: str) -> None:
        """Collect contributors with commit stats."""
        url = f"{GITHUB_API}/repos/{repo}/stats/contributors"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, list):
            return
        for entry in data:
            author = entry.get("author", {})
            username = author.get("login", "")
            total = entry.get("total", 0)
            weeks = entry.get("weeks", [])
            adds = sum(w.get("a", 0) for w in weeks)
            dels = sum(w.get("d", 0) for w in weeks)
            if username:
                await self.db.upsert_contributor(
                    repo, username, commits=total, additions=adds, deletions=dels
                )

    async def collect_metadata(self, repo: str) -> None:
        """Collect rich metadata for a repository."""
        # --- Core repo info ---
        response = await self._request(f"{GITHUB_API}/repos/{repo}")
        if response is None:
            return

        data = response.json()
        license_info = data.get("license") or {}
        license_id = license_info.get("spdx_id", "") or ""

        topics_raw = data.get("topics") or []
        topics = ",".join(topics_raw)

        metadata: dict = {
            "description": data.get("description") or "",
            "language": data.get("language") or "",
            "stars": data.get("stargazers_count", 0),
            "forks": data.get("forks_count", 0),
            "watchers_count": data.get("subscribers_count", 0),
            "open_issues_count": data.get("open_issues_count", 0),
            "size_kb": data.get("size", 0),
            "license": license_id,
            "topics": topics,
            "created_at": data.get("created_at", ""),
            "updated_at": data.get("updated_at", ""),
            "pushed_at": data.get("pushed_at", ""),
            "default_branch": data.get("default_branch", "main"),
            "homepage": data.get("homepage") or "",
        }

        # --- Total commits via Link header trick ---
        try:
            commit_resp = await self._request(
                f"{GITHUB_API}/repos/{repo}/commits?per_page=1"
            )
            if commit_resp is not None:
                link_header = commit_resp.headers.get("Link", "")
                total_commits = 0
                # Link: <...?page=N>; rel="last"
                for part in link_header.split(","):
                    part = part.strip()
                    if 'rel="last"' in part:
                        # Extract page number from URL
                        url_part = part.split(";")[0].strip().strip("<>")
                        for param in url_part.split("&"):
                            if param.startswith("page="):
                                total_commits = int(param.split("=", 1)[1])
                                break
                        break
                metadata["total_commits"] = total_commits
        except Exception:
            logger.warning("Could not get commit count for %s", repo)

        # --- Releases count ---
        try:
            releases_resp = await self._request(
                f"{GITHUB_API}/repos/{repo}/releases?per_page=1"
            )
            if releases_resp is not None:
                link_header = releases_resp.headers.get("Link", "")
                releases_count = len(releases_resp.json())
                for part in link_header.split(","):
                    part = part.strip()
                    if 'rel="last"' in part:
                        url_part = part.split(";")[0].strip().strip("<>")
                        for param in url_part.split("&"):
                            if param.startswith("page="):
                                releases_count = int(param.split("=", 1)[1])
                                break
                        break
                metadata["releases_count"] = releases_count
        except Exception:
            logger.warning("Could not get releases count for %s", repo)

        # --- Language breakdown ---
        try:
            lang_resp = await self._request(
                f"{GITHUB_API}/repos/{repo}/languages"
            )
            if lang_resp is not None:
                metadata["languages_json"] = json.dumps(lang_resp.json())
        except Exception:
            logger.warning("Could not get languages for %s", repo)

        await self.db.upsert_repo_metadata(repo, **metadata)

    async def collect_commit_activity(self, repo: str) -> None:
        """Collect 52-week commit activity histogram for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/stats/commit_activity"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, list):
            return
        for week in data:
            week_ts = week.get("week", 0)
            days = json.dumps(week.get("days", [0] * 7))
            total = week.get("total", 0)
            await self.db.upsert_commit_activity(repo, week_ts, days, total)

    async def collect_code_frequency(self, repo: str) -> None:
        """Collect weekly additions/deletions totals for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/stats/code_frequency"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, list):
            return
        for entry in data:
            # Each entry is [week_timestamp, additions, deletions]
            if len(entry) >= 3:
                week_ts = entry[0]
                additions = entry[1]
                deletions = abs(entry[2])  # GitHub returns negative for deletions
                await self.db.upsert_code_frequency(repo, week_ts, additions, deletions)

    async def collect_community_profile(self, repo: str) -> None:
        """Collect community health profile for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/community/profile"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        health_percentage = data.get("health_percentage", 0)
        await self.db.upsert_repo_metadata(repo, health_percentage=health_percentage)

    async def collect_releases(self, repo: str) -> None:
        """Collect releases and per-asset download counts."""
        url = f"{GITHUB_API}/repos/{repo}/releases?per_page=100"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, list):
            return
        for release in data:
            tag = release.get("tag_name", "")
            if not tag:
                continue
            for asset in release.get("assets", []):
                asset_name = asset.get("name", "")
                if not asset_name:
                    continue
                await self.db.upsert_release_asset(
                    repo_name=repo,
                    release_tag=tag,
                    asset_name=asset_name,
                    download_count=asset.get("download_count", 0),
                    size_bytes=asset.get("size", 0),
                    created_at=asset.get("created_at", ""),
                )

    async def collect_issues(self, repo: str) -> None:
        """Collect open and recently closed issues and PRs."""
        for state in ("open", "closed"):
            url = f"{GITHUB_API}/repos/{repo}/issues?state={state}&per_page=30&sort=updated"
            response = await self._request(url)
            if response is None:
                continue
            for item in response.json():
                is_pr = "pull_request" in item
                user = item.get("user", {})
                label_names = ",".join(
                    lb.get("name", "") for lb in item.get("labels", [])
                )
                await self.db.upsert_issue(
                    repo,
                    item["number"],
                    item.get("title", ""),
                    item.get("state", ""),
                    user.get("login", ""),
                    label_names,
                    item.get("created_at", ""),
                    item.get("closed_at"),
                    is_pr=is_pr,
                )

    async def collect_graphql_summary(self, repos: list[str]) -> None:
        """Fetch aggregate stats for all repos in a single GraphQL query.

        Retrieves stargazerCount, forkCount, open issues/PRs, releases, and
        discussions counts, then updates repo_metadata for each repo found.
        """
        self._check_rate_limit()
        client = await self._get_client()

        # Build per-repo fragment aliases — GraphQL field names cannot contain "/"
        fragments = []
        alias_map: dict[str, str] = {}
        for i, repo in enumerate(repos):
            parts = repo.split("/", 1)
            if len(parts) != 2:
                continue
            owner, name = parts
            alias = f"repo{i}"
            alias_map[alias] = repo
            fragments.append(f"""
  {alias}: repository(owner: "{owner}", name: "{name}") {{
    stargazerCount
    forkCount
    issues(states: OPEN) {{ totalCount }}
    pullRequests(states: OPEN) {{ totalCount }}
    releases {{ totalCount }}
    discussions {{ totalCount }}
  }}""")

        if not fragments:
            return

        query = "query {" + "".join(fragments) + "\n}"
        response = await client.post(
            GITHUB_GRAPHQL,
            json={"query": query},
        )
        self._update_rate_limit(response)
        response.raise_for_status()

        result = response.json()
        gql_data = result.get("data") or {}
        for alias, repo in alias_map.items():
            repo_data = gql_data.get(alias)
            if not repo_data:
                continue
            await self.db.upsert_repo_metadata(
                repo,
                stars=repo_data.get("stargazerCount", 0),
                forks=repo_data.get("forkCount", 0),
                open_issues_count=repo_data.get("issues", {}).get("totalCount", 0),
                releases_count=repo_data.get("releases", {}).get("totalCount", 0),
            )

    async def collect_all(self) -> None:
        """Collect all data for all configured repositories."""
        for repo in self.repos:
            try:
                await self.collect_views(repo)
                await self.collect_clones(repo)
                await self.collect_referrers(repo)
                await self.collect_paths(repo)
                for people_fn in (
                    self.collect_stargazers,
                    self.collect_watchers,
                    self.collect_forkers,
                    self.collect_contributors,
                    self.collect_issues,
                    self.collect_metadata,
                    self.collect_commit_activity,
                    self.collect_code_frequency,
                    self.collect_community_profile,
                    self.collect_releases,
                ):
                    try:
                        await people_fn(repo)
                    except Exception:
                        logger.warning("Failed %s for %s", people_fn.__name__, repo)
            except RateLimitError:
                logger.warning("Rate limit reached, stopping collection")
                break
            except Exception:
                logger.exception("Error collecting data for %s", repo)
                continue

        # GraphQL bulk summary after per-repo loop
        try:
            await self.collect_graphql_summary(self.repos)
        except Exception:
            logger.warning("Failed collect_graphql_summary")
