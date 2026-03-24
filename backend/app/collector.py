"""GitHub traffic data collector — archives metrics before the 14-day expiry."""

import asyncio
import json
import logging
import os
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
        self._social_client: httpx.AsyncClient | None = None

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
        if self._social_client:
            await self._social_client.aclose()
            self._social_client = None

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

        # --- Security and analysis config ---
        security_and_analysis = data.get("security_and_analysis")
        if security_and_analysis is not None:
            metadata["security_config_json"] = json.dumps(security_and_analysis)

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

    async def _get_social_client(self) -> httpx.AsyncClient:
        if self._social_client is None:
            self._social_client = httpx.AsyncClient(
                headers={"User-Agent": "gh-tracker/1.0 (self-hosted analytics)"},
                timeout=15.0,
            )
        return self._social_client

    async def collect_social_mentions(self, repo: str) -> None:
        """Collect social mentions from Hacker News, Reddit, and Dev.to."""
        client = await self._get_social_client()
        parts = repo.split("/", 1)
        repo_name_slug = parts[1].lower() if len(parts) == 2 else repo.lower()

        # --- Hacker News ---
        try:
            hn_url = f"https://hn.algolia.com/api/v1/search?query=github.com/{repo}&tags=story"
            resp = await client.get(hn_url)
            resp.raise_for_status()
            for hit in resp.json().get("hits", []):
                url = hit.get("url") or ""
                title = hit.get("title") or ""
                score = hit.get("points") or 0
                author = hit.get("author") or ""
                if url:
                    await self.db.upsert_social_mention(
                        repo, "hackernews", url, title=title, score=score, author=author
                    )
        except Exception:
            logger.warning("Could not collect HN mentions for %s", repo)

        # --- Reddit ---
        try:
            reddit_url = (
                f"https://www.reddit.com/search.json"
                f"?q=github.com/{repo}&sort=new&limit=10"
            )
            resp = await client.get(reddit_url)
            resp.raise_for_status()
            for child in resp.json().get("data", {}).get("children", []):
                post = child.get("data", {})
                url = post.get("url") or ""
                title = post.get("title") or ""
                score = post.get("score") or 0
                author = post.get("author") or ""
                permalink = post.get("permalink") or ""
                # Use full Reddit post URL as the canonical URL if available
                post_url = f"https://www.reddit.com{permalink}" if permalink else url
                if post_url:
                    await self.db.upsert_social_mention(
                        repo, "reddit", post_url, title=title, score=score, author=author
                    )
        except Exception:
            logger.warning("Could not collect Reddit mentions for %s", repo)

        # --- Dev.to ---
        try:
            devto_url = (
                f"https://dev.to/api/articles?tag={repo_name_slug}&per_page=5"
            )
            resp = await client.get(devto_url)
            resp.raise_for_status()
            for article in resp.json():
                url = article.get("url") or ""
                title = article.get("title") or ""
                score = article.get("positive_reactions_count") or 0
                author_obj = article.get("user") or {}
                author = author_obj.get("username") or ""
                if url:
                    await self.db.upsert_social_mention(
                        repo, "devto", url, title=title, score=score, author=author
                    )
        except Exception:
            logger.warning("Could not collect Dev.to mentions for %s", repo)

    async def collect_scorecard(self, repo: str) -> None:
        """Collect OpenSSF Scorecard data for a repository."""
        parts = repo.split("/", 1)
        if len(parts) != 2:
            return
        owner, name = parts
        client = await self._get_social_client()
        try:
            url = f"https://api.scorecard.dev/projects/github.com/{owner}/{name}"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            score = data.get("score", -1)
            scorecard_json = json.dumps(data)
            await self.db.upsert_repo_metadata(
                repo,
                scorecard_score=score,
                scorecard_json=scorecard_json,
            )
        except Exception:
            logger.warning("Could not collect Scorecard data for %s", repo)

    async def collect_libraries_io(self, repo: str) -> None:
        """Collect Libraries.io data for a repository (requires LIBRARIES_IO_KEY)."""
        api_key = os.environ.get("LIBRARIES_IO_KEY")
        if not api_key:
            return
        parts = repo.split("/", 1)
        if len(parts) != 2:
            return
        owner, name = parts
        client = await self._get_social_client()
        try:
            url = f"https://libraries.io/api/github/{owner}/{name}?api_key={api_key}"
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
            dependent_repos_count = data.get("dependent_repos_count") or 0
            source_rank = data.get("rank") or 0
            await self.db.upsert_repo_metadata(
                repo,
                dependent_repos_count=dependent_repos_count,
                source_rank=source_rank,
            )
        except Exception:
            logger.warning("Could not collect Libraries.io data for %s", repo)

    async def detect_watcher_changes(self, repo: str) -> None:
        """Compare current watchers on GitHub against the DB, storing additions/removals."""
        url = f"{GITHUB_API}/repos/{repo}/subscribers"
        response = await self._request(url)
        if response is None:
            return

        current_usernames = {
            user.get("login", "")
            for user in response.json()
            if user.get("login")
        }

        existing_rows = await self.db.get_watchers(repo)
        existing_usernames = {row["username"] for row in existing_rows}

        added = current_usernames - existing_usernames
        removed = existing_usernames - current_usernames

        for username in added:
            await self.db.upsert_watcher(repo, username)
            await self.db.store_watcher_change(repo, username, "added")

        for username in removed:
            await self.db.store_watcher_change(repo, username, "removed")

    async def collect_citations(self, repo: str) -> None:
        """Collect academic citations from Semantic Scholar and OpenAlex."""
        client = await self._get_social_client()

        # --- Semantic Scholar ---
        try:
            ss_url = (
                f"https://api.semanticscholar.org/graph/v1/paper/search"
                f"?query=github.com/{repo}&limit=5"
                f"&fields=title,authors,year,citationCount,externalIds"
            )
            resp = await client.get(ss_url)
            resp.raise_for_status()
            for paper in resp.json().get("data", []):
                paper_id = paper.get("paperId") or ""
                title = paper.get("title") or ""
                authors_list = paper.get("authors") or []
                authors = ", ".join(a.get("name", "") for a in authors_list)
                year = paper.get("year") or 0
                citation_count = paper.get("citationCount") or 0
                url = (
                    f"https://www.semanticscholar.org/paper/{paper_id}"
                    if paper_id
                    else ""
                )
                if url:
                    await self.db.upsert_citation(
                        repo, "semantic_scholar", url,
                        title=title, authors=authors,
                        year=year, citation_count=citation_count,
                    )
        except Exception:
            logger.warning("Could not collect Semantic Scholar citations for %s", repo)

        # --- OpenAlex ---
        try:
            oa_url = (
                f"https://api.openalex.org/works"
                f"?search=github.com/{repo}&per_page=5"
            )
            resp = await client.get(oa_url)
            resp.raise_for_status()
            for work in resp.json().get("results", []):
                work_id = work.get("id") or ""
                title = work.get("title") or ""
                authorships = work.get("authorships") or []
                authors = ", ".join(
                    a.get("author", {}).get("display_name", "")
                    for a in authorships
                )
                pub_year = work.get("publication_year") or 0
                citation_count = work.get("cited_by_count") or 0
                url = work_id  # OpenAlex ID is a URL
                if url:
                    await self.db.upsert_citation(
                        repo, "openalex", url,
                        title=title, authors=authors,
                        year=pub_year, citation_count=citation_count,
                    )
        except Exception:
            logger.warning("Could not collect OpenAlex citations for %s", repo)

    async def collect_workflow_runs(self, repo: str) -> None:
        """Collect the 30 most recent CI workflow runs for a repository."""
        url = f"{GITHUB_API}/repos/{repo}/actions/runs?per_page=30"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, dict):
            return
        for run in data.get("workflow_runs", []):
            run_id = run.get("id", 0)
            if not run_id:
                continue
            workflow_name = run.get("name") or ""
            status = run.get("status") or ""
            conclusion = run.get("conclusion") or ""
            event = run.get("event") or ""
            branch = run.get("head_branch") or ""
            created_at = run.get("created_at") or ""
            run_started_at = run.get("run_started_at") or ""
            updated_at = run.get("updated_at") or ""

            # Calculate duration from run_started_at to updated_at
            duration_seconds = 0
            try:
                if run_started_at and updated_at:
                    start = datetime.fromisoformat(run_started_at.replace("Z", "+00:00"))
                    end = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
                    duration_seconds = max(0, int((end - start).total_seconds()))
            except (ValueError, TypeError):
                pass

            await self.db.upsert_workflow_run(
                repo_name=repo,
                run_id=run_id,
                workflow_name=workflow_name,
                status=status,
                conclusion=conclusion,
                event=event,
                branch=branch,
                created_at=created_at,
                run_started_at=run_started_at,
                updated_at=updated_at,
                duration_seconds=duration_seconds,
            )

    async def collect_punch_card(self, repo: str) -> None:
        """Collect commit time punch-card data (168 entries: 7 days x 24 hours)."""
        url = f"{GITHUB_API}/repos/{repo}/stats/punch_card"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, list):
            return
        for entry in data:
            # Each entry is [day, hour, commits]
            if len(entry) >= 3:
                day, hour, commits = entry[0], entry[1], entry[2]
                await self.db.upsert_punch_card(repo, day, hour, commits)

    async def collect_participation(self, repo: str) -> None:
        """Collect 52-week owner vs. community participation stats."""
        url = f"{GITHUB_API}/repos/{repo}/stats/participation"
        response = await self._request(url)
        if response is None:
            return
        data = response.json()
        if not isinstance(data, dict):
            return
        all_commits = data.get("all", [])
        owner_commits = data.get("owner", [])
        if not isinstance(all_commits, list) or not isinstance(owner_commits, list):
            return
        for week_offset, (all_c, owner_c) in enumerate(zip(all_commits, owner_commits)):
            await self.db.upsert_participation(repo, week_offset, all_c, owner_c)

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
                    self.collect_social_mentions,
                    self.collect_scorecard,
                    self.collect_libraries_io,
                    self.collect_citations,
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
