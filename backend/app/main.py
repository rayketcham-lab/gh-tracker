"""FastAPI application for the GitHub analytics dashboard."""

import csv
import io
import json

from fastapi import FastAPI, Query
from fastapi.responses import StreamingResponse

from app.database import Database


def create_app(db: Database | None = None) -> FastAPI:
    app = FastAPI(title="gh-tracker", version="0.1.0")

    app.state.db = db

    @app.get("/api/health")
    async def health() -> dict:
        return {"status": "ok"}

    @app.get("/api/repos")
    async def list_repos() -> list[str]:
        return await app.state.db.list_repos()

    @app.get("/api/repos/{owner}/{repo}/traffic")
    async def get_traffic(
        owner: str,
        repo: str,
        start: str | None = Query(None),
        end: str | None = Query(None),
    ) -> list[dict]:
        repo_name = f"{owner}/{repo}"
        start_date = start or "2000-01-01"
        end_date = end or "2099-12-31"
        return await app.state.db.get_daily_metrics(repo_name, start_date, end_date)

    @app.get("/api/repos/{owner}/{repo}/referrers")
    async def get_referrers(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_referrers(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/paths")
    async def get_paths(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_popular_paths(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/summary")
    async def get_repo_summary(owner: str, repo: str) -> dict:
        repo_name = f"{owner}/{repo}"
        traffic = await app.state.db.get_daily_metrics(
            repo_name, "2000-01-01", "2099-12-31"
        )
        referrers = await app.state.db.get_referrers(repo_name)
        paths = await app.state.db.get_popular_paths(repo_name)
        total_views = sum(d["views"] for d in traffic)
        total_uv = sum(d["unique_visitors"] for d in traffic)
        return {
            "repo_name": repo_name,
            "github_url": f"https://github.com/{repo_name}",
            "traffic": traffic,
            "referrers": referrers,
            "paths": paths,
            "total_views": total_views,
            "total_unique_visitors": total_uv,
        }

    @app.get("/api/repos/{owner}/{repo}/visitors")
    async def get_repo_visitors(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_repo_visitors(f"{owner}/{repo}")

    @app.get("/api/visitors")
    async def get_visitors(repo: str | None = Query(None)) -> list[dict]:
        return await app.state.db.get_daily_visitors(repo)

    @app.get("/api/visitors/summary")
    async def get_visitors_summary() -> list[dict]:
        return await app.state.db.get_visitor_summary()

    # --- People endpoints ---

    @app.get("/api/repos/{owner}/{repo}/stargazers")
    async def get_stargazers(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_stargazers(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/watchers")
    async def get_watchers(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_watchers(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/forkers")
    async def get_forkers(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_forkers(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/contributors")
    async def get_contributors(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_contributors(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/people")
    async def get_people_summary(owner: str, repo: str) -> dict:
        repo_name = f"{owner}/{repo}"
        stars = await app.state.db.get_stargazers(repo_name)
        watchers = await app.state.db.get_watchers(repo_name)
        forkers = await app.state.db.get_forkers(repo_name)
        contribs = await app.state.db.get_contributors(repo_name)
        return {
            "repo_name": repo_name,
            "stargazers_count": len(stars),
            "watchers_count": len(watchers),
            "forkers_count": len(forkers),
            "contributors_count": len(contribs),
            "recent_stargazers": stars[:10],
            "recent_forkers": forkers[:10],
            "top_contributors": contribs[:10],
        }

    # --- Metadata endpoints ---

    @app.get("/api/repos/{owner}/{repo}/metadata")
    async def get_metadata(owner: str, repo: str) -> dict:
        repo_name = f"{owner}/{repo}"
        meta = await app.state.db.get_repo_metadata(repo_name)
        if meta is None:
            return {
                "repo_name": repo_name,
                "description": "",
                "language": "",
                "topics": "",
                "stars": 0,
                "forks": 0,
                "watchers_count": 0,
                "open_issues_count": 0,
                "size_kb": 0,
                "license": "",
                "created_at": "",
                "updated_at": "",
                "pushed_at": "",
                "default_branch": "main",
                "homepage": "",
                "total_commits": 0,
                "releases_count": 0,
                "languages_json": "{}",
                "collected_at": "",
                "health_percentage": 0,
            }
        return meta

    @app.get("/api/metadata")
    async def get_all_metadata() -> list[dict]:
        return await app.state.db.get_all_repo_metadata()

    # --- Issues endpoints ---

    @app.get("/api/repos/{owner}/{repo}/issues/summary")
    async def get_issues_summary(owner: str, repo: str) -> dict:
        return await app.state.db.get_issue_summary(f"{owner}/{repo}")

    @app.get("/api/repos/{owner}/{repo}/issues")
    async def get_issues(
        owner: str, repo: str, state: str | None = Query(None)
    ) -> list[dict]:
        return await app.state.db.get_issues(
            f"{owner}/{repo}", state=state
        )

    # --- Repository statistics endpoints (Feature 2) ---

    @app.get("/api/repos/{owner}/{repo}/commit-activity")
    async def get_commit_activity(owner: str, repo: str) -> list[dict]:
        rows = await app.state.db.get_commit_activity(f"{owner}/{repo}")
        result = []
        for row in rows:
            days_raw = row.get("days", "[]")
            try:
                days = json.loads(days_raw) if isinstance(days_raw, str) else days_raw
            except (ValueError, TypeError):
                days = [0, 0, 0, 0, 0, 0, 0]
            result.append({
                "week_timestamp": row["week_timestamp"],
                "days": days,
                "total": row.get("total", 0),
            })
        return result

    @app.get("/api/repos/{owner}/{repo}/code-frequency")
    async def get_code_frequency(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_code_frequency(f"{owner}/{repo}")

    # --- Release download tracking endpoint (Feature 4) ---

    @app.get("/api/repos/{owner}/{repo}/releases")
    async def get_releases(owner: str, repo: str) -> list[dict]:
        return await app.state.db.get_release_assets(f"{owner}/{repo}")

    # --- CSV/JSON export endpoints (Feature 5) ---

    @app.get("/api/export/traffic")
    async def export_traffic(fmt: str = Query("json", alias="format")) -> StreamingResponse:
        rows = await app.state.db.get_all_daily_metrics()
        if fmt == "csv":
            output = io.StringIO()
            if rows:
                writer = csv.DictWriter(output, fieldnames=list(rows[0].keys()))
                writer.writeheader()
                writer.writerows(rows)
            else:
                output.write("")
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=traffic.csv"},
            )
        # Default: JSON
        return StreamingResponse(
            iter([json.dumps(rows)]),
            media_type="application/json",
        )

    @app.get("/api/export/people")
    async def export_people(fmt: str = Query("json", alias="format")) -> StreamingResponse:
        stargazers = await app.state.db.get_all_stargazers()
        contributors = await app.state.db.get_all_contributors()

        if fmt == "csv":
            output = io.StringIO()
            writer = csv.writer(output)
            writer.writerow(["repo_name", "username", "type", "starred_at",
                             "commits", "additions", "deletions"])
            for s in stargazers:
                writer.writerow([
                    s["repo_name"], s["username"], "stargazer",
                    s.get("starred_at", ""), "", "", "",
                ])
            for c in contributors:
                writer.writerow([
                    c["repo_name"], c["username"], "contributor",
                    "", c["commits"], c["additions"], c["deletions"],
                ])
            output.seek(0)
            return StreamingResponse(
                iter([output.getvalue()]),
                media_type="text/csv",
                headers={"Content-Disposition": "attachment; filename=people.csv"},
            )
        # Default: JSON
        return StreamingResponse(
            iter([json.dumps({"stargazers": stargazers, "contributors": contributors})]),
            media_type="application/json",
        )

    return app
