# Development Guide

This guide is the technical reference for contributors. For the shortest clone-to-run path, use the root `README.md`.

## Current Architecture

Active runtime:
- Backend entrypoint: `backend/app/main.py`
- Frontend app: `frontend/src/App.jsx`
- Database: Postgres
- Local orchestration: `docker-compose.yml`

Request flow:
1. The React frontend calls the backend through `frontend/src/lib/api.js`.
2. FastAPI routes live in `backend/app/routes/`.
3. Core gameplay lives in `backend/app/services/game_service.py` plus the mixins in `game_play.py` and `game_insights.py`.
4. Recommendation state is built with category-aware features from `backend/app/category_profiles.py`.
5. Model refresh and shared recommendation state live in `backend/app/services/recommender.py`.

## Current Product Surface

Implemented:
- Postgres-first backend with category-aware gameplay.
- Supported categories: `fountain_pens`, `movies`, `games`.
- Account-based auth with expiring session tokens.
- Admin APIs and frontend admin screen.
- Classic gameplay plus beta-mode preference seeding.
- Editable preference deck during active redesigned sessions.
- Hidden preference detection and end-of-game explainability.

Important runtime details:
- The frontend currently starts games in `beta` mode from `frontend/src/App.jsx`.
- Categories need at least 100 visible items before the frontend will treat them as ready.
- Onboarding serves a 100-item pool and allows selecting 1 to 10 items.
- Standard rounds currently show 10 candidates.

## Data Model

Primary Postgres tables:
- `products`
- `users`
- `games`
- `game_rounds`
- `prefix_ratings`

Product records are category-aware:
- `ProductRecord.category` stores the normalized category id.
- `ProductRecord.data` stores the category-specific payload.

Schema and startup helpers:
- `backend/app/services/schema_service.py`
- `backend/app/services/ml_config.py`
- `backend/app/services/recommender.py`

## Local Workflows

### Docker-first workflow

From the repo root:

```bash
docker compose up --build -d postgres backend
docker compose exec backend python -m scripts.load_db
docker compose --profile local-frontend up -d --build frontend
```

### Python/Node workflow

Backend:

```bash
cd backend
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host localhost --port 8015 --reload
```

Frontend:

```bash
cd frontend
npm install
npm run dev
```

Notes:
- Copy `backend/.env.example` to `backend/.env` before running locally without Docker.
- `DATABASE_URL` must point to a working Postgres instance.

## Script Catalog

Run from `backend/` unless noted otherwise.

Core scripts:
- `python -m scripts.load_db`
  - loads the bundled fountain pen dataset
- `python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8`
  - ingests movies from TMDB
- `python -m scripts.ingest_games_igdb --max-candidates 5000`
  - ingests games from IGDB
- `python -m scripts.migrate_multicategory_schema`
  - compatibility migration helper
- `python -m scripts.evaluate_pbcf`
  - evaluates AI performance on completed games

Utility script:
- `python test.py summary`
- `python test.py list-collections`
- `python test.py clear-games`
- `python test.py clear-products --category movies`
- `python test.py export-movies-json --output data/movies_export.json`
- `python test.py export-movies-excel --output data/movies_export.csv`

## Testing

Backend tests:

```bash
cd backend
python -m unittest discover -s tests -v
```

Compile sanity:

```bash
cd backend
python -m compileall app scripts tests
```

Frontend build:

```bash
cd frontend
npm run build
```

## Operational Notes

TMDB ingest:
- checkpoint file: `backend/data/tmdb_ingest_checkpoint.json`
- supports `--no-resume`
- supports `--max-pages-per-lane`
- supports `--lane-bars`

IGDB ingest:
- checkpoint file: `backend/data/igdb_ingest_checkpoint.json`
- supports `--no-resume`
- supports `--max-pages-per-lane`
- supports `--detail-batch-size`
- supports `--lane-bars`

Full ingestion argument reference:
- `docs/INGESTION_GUIDE.md`

## Common Issues

Pens not visible:
- run `python -m scripts.load_db`

Category not ready in frontend:
- the frontend expects at least 100 visible items for that category

Movie or game ingest unavailable:
- confirm the matching API credentials exist in `backend/.env`

Postgres connection failure:
- verify Postgres is running
- verify `DATABASE_URL`

## Recommended Doc Split

This file is for contributor workflows and architecture.

Use:
- `README.md` for quick start
- `docs/API_REFERENCE.md` for routes
- `docs/FEATURES_GUIDE.md` for user-facing behavior
- `docs/ADDING_DATASETS.md` for category extension
- `docs/INGESTION_GUIDE.md` for TMDB and IGDB script flags
- `docs/DB_SYNC.md` for copying Postgres data from the VM Docker database into local Docker
- `docs/NGINX_SETUP.md` for deployment and backup notes
