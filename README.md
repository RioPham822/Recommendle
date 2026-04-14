# Recommendle

Recommendle is a web game where a human player competes against an AI recommendation model over a sequence of choices. The project explores sequential preference modeling: learning taste from onboarding picks, round-by-round selections, and lightweight negative feedback instead of one-off ratings alone.

Live site: `https://recommendle-frontend.onrender.com`

## What You Can Do

- Play category-based recommendation rounds for:
  - `fountain_pens`
  - `movies`
  - `games`
- Create an account and keep separate play history.
- Use the beta flow to seed preferences before onboarding.
- Compare your picks against the AI each round.
- Review final summaries, learned preferences, and hidden-gem recommendations.
- Use the admin screen to inspect users, product catalogs, and ML config.

## Quick Start

Prerequisites:
- Docker Desktop or Docker Engine with Docker Compose
- Git

From the repo root:

```bash
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git
cd 2026Spring-Team42-Decidio-3
docker compose up --build -d postgres backend
docker compose exec backend python -m scripts.load_db
docker compose --profile local-frontend up -d --build frontend
```

Open:
- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8015`

Optional Windows helper:

```bat
start.bat
```

`start.bat` starts Postgres and the backend, seeds fountain pens, then starts the local frontend container.

## Common Tasks

Load fountain pens:

```bash
docker compose exec backend python -m scripts.load_db
```

Ingest movies:

```bash
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
```

Ingest games:

```bash
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
```

Check available categories:

```bash
curl http://localhost:8015/api/game/categories
```

Stop services:

```bash
docker compose down
```

Remove Postgres volume too:

```bash
docker compose down -v
```

## Docs

- [Development Guide](docs/DEVELOPMENT.md)
- [Testing Overview](docs/TESTING_OVERVIEW.md)
- [API Reference](docs/API_REFERENCE.md)
- [Features Guide](docs/FEATURES_GUIDE.md)
- [Adding Datasets](docs/ADDING_DATASETS.md)
- [Ingestion Guide](docs/INGESTION_GUIDE.md)
- [Nginx Setup](docs/NGINX_SETUP.md)
- [Requirements](docs/REQUIREMENTS.md)

## Tech Stack

- Frontend: React 18 + Vite + MUI
- Backend: FastAPI + SQLAlchemy + asyncpg
- Database: Postgres
- Model: prefix-based collaborative filtering with category-aware feature extraction

## Repository Layout

```text
backend/
  app/
    main.py
    routes/
    services/
    ml/
  data/
  scripts/
  tests/
frontend/
  src/
docs/
docker-compose.yml
start.bat
```

## Notes

- The project is Postgres-only. Deprecated MongoDB docs have been removed.
- The fountain pen dataset is included in the repo and is the fastest way to get a playable local setup.
- Movies and games require API credentials in `backend/.env` before ingestion.

## License

Developed as part of CSC 492 senior design coursework.
