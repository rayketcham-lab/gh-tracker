"""Run the gh-tracker API server."""

import asyncio
import os

import uvicorn

from app.database import Database
from app.main import create_app
from app.server_config import get_server_port

DB_PATH = os.environ.get("GH_TRACKER_DB", "../data/metrics.db")


async def main() -> None:
    db = Database(DB_PATH)
    await db.initialize()

    app = create_app(db=db)

    config = uvicorn.Config(
        app,
        host="0.0.0.0",
        port=get_server_port(),
        log_level="info",
    )
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
