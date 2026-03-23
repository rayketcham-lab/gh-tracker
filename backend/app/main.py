"""FastAPI application for the GitHub analytics dashboard."""

from fastapi import FastAPI, Query

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

    return app
