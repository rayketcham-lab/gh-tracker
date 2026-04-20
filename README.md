<div align="center">

[![CI](https://github.com/rayketcham/gh-tracker/actions/workflows/ci.yml/badge.svg)](https://github.com/rayketcham/gh-tracker/actions/workflows/ci.yml)
![Python 3.12](https://img.shields.io/badge/python-3.12-3776AB?logo=python&logoColor=white)
![React 18](https://img.shields.io/badge/react-18-61DAFB?logo=react&logoColor=white)
![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)
![SQLite](https://img.shields.io/badge/SQLite-003B57?logo=sqlite&logoColor=white)
![License](https://img.shields.io/badge/license-MIT-green)
![Tests](https://img.shields.io/badge/tests-146%20passing-brightgreen)
![Endpoints](https://img.shields.io/badge/API%20endpoints-23-blue)

# gh-tracker

<!-- runners-demo-hero -->
<p align="center">
  <img src="docs/runners-demo.gif" alt="gh-tracker dashboard tour: traffic, referrers, and self-hosted runners live view" width="900">
</p>


**Self-hosted GitHub analytics dashboard that captures every metric GitHub exposes — and preserves it forever.**

GitHub's Traffic API permanently deletes data after 14 days.<br>
gh-tracker archives it before that happens.

</div>

---

## What It Tracks

| Category | Metrics | Source |
|----------|---------|--------|
| **Traffic** | Views, unique visitors, clones, unique cloners (daily) | REST API (14-day archival) |
| **Referrers** | Top 10 traffic sources with view counts | REST API |
| **Popular Pages** | Most visited paths in your repos | REST API |
| **People** | Stargazers (with timestamps), watchers, forkers, contributors | REST + GraphQL |
| **Issues & PRs** | Open/closed counts, titles, authors, labels, timestamps | REST API |
| **Repo Metadata** | Description, language, topics, license, size, commit count | REST API |
| **Languages** | Full byte-count breakdown with GitHub colors | REST API |
| **Commit Activity** | 52-week commit histogram by day-of-week | REST API |
| **Code Frequency** | Weekly additions/deletions over time | REST API |
| **Releases** | Per-asset download counts, sizes, dates | REST API |
| **Community Health** | GitHub's health_percentage score | REST API |

## Dashboard Features

- **KPI Cards** — views, unique visitors, clones, all-time totals with trend indicators
- **Traffic Chart** — area chart with gradient fills showing views, visitors, clones over time
- **Repo Drill-Down** — click any repo to see:
  - Rich metadata header (description, language bar, topics, stats)
  - Commit heatmap (GitHub-style green squares, 52 weeks)
  - Code frequency chart (additions vs deletions)
  - Daily visitor breakdown with bar charts
  - People panel (stargazers, contributors, forkers with GitHub avatars)
  - Issues & PRs with color-coded status and labels
  - Language breakdown with colored segments
  - Release downloads per asset
- **Referrers Chart** — horizontal bar chart of traffic sources
- **Popular Pages** — table with ranked paths
- **CSV/JSON Export** — download all traffic and people data
- **Dark Theme** — cyan/emerald/violet accents, smooth animations

## Architecture

```
                    ┌─────────────────────────┐
                    │      GitHub APIs         │
                    │  REST · GraphQL · Events │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   Collector (Python)     │
                    │  ETag caching · retry    │
                    │  rate limit awareness    │
                    │  runs every 12h (systemd)│
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   SQLite (WAL mode)      │
                    │  15 tables · idempotent  │
                    │  raw response archival   │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   FastAPI (23 endpoints) │
                    │  async · Pydantic · CORS │
                    └──────────┬──────────────┘
                               │
                    ┌──────────▼──────────────┐
                    │   React Dashboard        │
                    │  Recharts · TanStack     │
                    │  Query · Dark theme      │
                    └─────────────────────────┘
```

## Quick Start

```bash
# Clone
git clone https://github.com/rayketcham/gh-tracker.git
cd gh-tracker

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"

# Collect data (uses `gh auth token` automatically)
GH_TRACKER_PUBLIC_ONLY=true python collect_live.py

# Start API server (defaults to port 50047 — override with GH_TRACKER_PORT)
python run.py                            # → http://localhost:50047
# GH_TRACKER_PORT=51234 python run.py    # pick your own port

# Frontend (separate terminal)
cd frontend
npm install
npm run dev   # → http://localhost:5173
```

> **Port choice.** The API defaults to **50047** — picked from the ephemeral/50000+ range
> so it won't collide with the usual suspects (8000/8080 dev servers, 3000 Node, 5000 Flask,
> 5173 Vite, etc.). Change it any time with `GH_TRACKER_PORT`.

## Configuration

| Environment Variable | Default | Description |
|---------------------|---------|-------------|
| `GH_TOKEN` | `gh auth token` | GitHub personal access token |
| `GH_TRACKER_REPOS` | auto-discover | Comma-separated `owner/repo` list |
| `GH_TRACKER_PUBLIC_ONLY` | `false` | Only track public repos |
| `GH_TRACKER_DB` | `data/metrics.db` | SQLite database path |
| `GH_TRACKER_PORT` | `50047` | API server port (any valid TCP port) |

## Automated Collection

```bash
# Install systemd timer (runs at 06:00 and 18:00 daily)
sudo cp backend/gh-tracker-collect.service /etc/systemd/system/
sudo cp backend/gh-tracker-collect.timer /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now gh-tracker-collect.timer
```

To also run the API as a service (overriding the default port if you like):

```bash
sudo cp backend/gh-tracker-api.service /etc/systemd/system/
# Edit the unit's Environment=GH_TRACKER_PORT=... line if you want a different port
sudo systemctl daemon-reload
sudo systemctl enable --now gh-tracker-api.service
```

## API Endpoints

<details>
<summary>23 endpoints (click to expand)</summary>

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| GET | `/api/repos` | List tracked repos |
| GET | `/api/metadata` | All repos metadata |
| GET | `/api/visitors` | Daily visitors (all repos) |
| GET | `/api/visitors/summary` | Per-repo visitor aggregation |
| GET | `/api/repos/{owner}/{repo}/traffic` | Daily traffic time series |
| GET | `/api/repos/{owner}/{repo}/referrers` | Top referral sources |
| GET | `/api/repos/{owner}/{repo}/paths` | Popular pages |
| GET | `/api/repos/{owner}/{repo}/visitors` | Daily visitor drill-down |
| GET | `/api/repos/{owner}/{repo}/summary` | Combined repo overview |
| GET | `/api/repos/{owner}/{repo}/metadata` | Repo metadata |
| GET | `/api/repos/{owner}/{repo}/stargazers` | Who starred |
| GET | `/api/repos/{owner}/{repo}/watchers` | Who's watching |
| GET | `/api/repos/{owner}/{repo}/forkers` | Who forked |
| GET | `/api/repos/{owner}/{repo}/contributors` | Who committed |
| GET | `/api/repos/{owner}/{repo}/people` | Combined people summary |
| GET | `/api/repos/{owner}/{repo}/issues/summary` | Issue/PR counts |
| GET | `/api/repos/{owner}/{repo}/issues` | Issue list (filterable) |
| GET | `/api/repos/{owner}/{repo}/commit-activity` | 52-week commit histogram |
| GET | `/api/repos/{owner}/{repo}/code-frequency` | Weekly adds/deletes |
| GET | `/api/repos/{owner}/{repo}/releases` | Release assets + downloads |
| GET | `/api/export/traffic` | Export traffic (CSV/JSON) |
| GET | `/api/export/people` | Export people (CSV/JSON) |

</details>

## Development

```bash
# Backend tests (146 passing)
cd backend && pytest tests/ --ignore=tests/test_live_collect.py -v

# Backend lint
cd backend && ruff check app/ tests/

# Frontend build
cd frontend && npm run build

# Frontend lint
cd frontend && npm run lint
```

## Project Structure

```
backend/
  app/
    collector.py       # GitHub API data collection (REST + GraphQL)
    config.py          # Token/repo discovery via gh CLI
    database.py        # SQLite with 15 tables, async via aiosqlite
    main.py            # FastAPI with 23 endpoints
    server_config.py   # Port resolution (GH_TRACKER_PORT, default 50047)
  tests/               # 146 unit tests (pytest + pytest-httpx)
  collect_live.py      # CLI entry point for data collection
  run.py               # API server entry point

frontend/
  src/
    components/     # 12 React components
      KpiCard.tsx CommitHeatmap.tsx CodeFrequencyChart.tsx
      TrafficChart.tsx ReferrersChart.tsx PopularPaths.tsx
      VisitorsTable.tsx VisitorDrilldown.tsx PeoplePanel.tsx
      IssuesPanel.tsx LanguageChart.tsx ReleasesPanel.tsx
      RepoHeader.tsx
    App.tsx          # Main dashboard layout
    api.ts           # API client

data/               # SQLite database (gitignored)
```

## Why This Exists

GitHub deletes traffic data after 14 days. If you don't archive it, it's gone forever. gh-tracker runs on a 12-hour timer, captures everything, and gives you a dashboard that shows the full picture — not just the last two weeks.

---

<div align="center">

Built with [Claude Code](https://claude.ai/code)

</div>
