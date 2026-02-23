# Recommendle

Recommendle is an interactive web game where a human player competes against an AI recommendation model.  
It is a CSC 492 Senior Design project focused on **sequential preference modeling**: learning user taste from a sequence of choices instead of one-off ratings.

## What The Program Currently Does
- Runs a web game with:
  - onboarding: select 10 items from a pool of 50
  - 5 gameplay rounds with 10 candidates per round
  - AI-vs-human scoring each round
  - final summary with explainability and recommendations
- Supports category-aware gameplay:
  - `fountain_pens` (included in repo and loadable immediately)
  - `movies` (loadable via TMDB ingestion script)
- Uses **Postgres** as the active backend for the app (`app.main`).
- Provides two exploration modes in UI:
  - visual mode
  - feature mode
- Tracks leaderboard and player history by category.
- Detects hidden/latent preference patterns and surfaces "hidden gems."

## ✨ NEW FEATURES (Feb 2026)
- **Excel/CSV Export**: Export database collections to Excel-compatible CSV format
  - Interactive menu for easy selection
  - Command-line support for scripting
  - All data in `./data/exports/`
- **User Authentication**: Username/password login system for multiple independent players
  - Secure registration & login endpoints
  - Session token management (7-day expiry)
  - User accounts with game history tracking
  - Password hashing with PBKDF2 (100,000 iterations)

See [FEATURES_GUIDE.md](docs/FEATURES_GUIDE.md) for detailed usage.
Dataset extension guide: [ADDING_DATASETS.md](docs/ADDING_DATASETS.md)

## Tech Stack
- Frontend: React 18 + Vite + CSS
- Backend: FastAPI + Uvicorn (Python)
- Database: Postgres (SQLAlchemy + asyncpg)
- Model: Prefix-based collaborative filtering with sequential updates

## Repository Layout
```text
backend/
  app/
    main.py              # Active FastAPI app (Postgres)
    routes/game.py             # Game API endpoints
    services/game_service.py   # Core game logic
    ml/prefix_cf.py            # Preference model + hidden preference logic
  data/
    products.json              # Fountain pen catalog in repo
  scripts/
    load_db.py                 # Loads fountain pens into Postgres-backed store
    ingest_movies_tmdb.py      # Ingests movies from TMDB into Postgres
    migrate_multicategory_schema.py
frontend/
  src/
start.bat                      # Convenience launcher (Windows)
```

## Prerequisites
- Docker Desktop (Windows/macOS) or Docker Engine + Docker Compose plugin (Linux)
- Git

---

## Setup From Clone (Docker First)

### 1. Clone
```bash
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git
cd 2026Spring-Team42-Decidio-3
```

### 2. Start full stack (Postgres + backend + frontend)
From repo root:
```bash
docker compose up --build -d
```

### 3. Load the fountain pen dataset (required once per new database)
From repo root:
```bash
docker compose exec backend python -m scripts.load_db
```

Important:
- This seeds the required `fountain_pens` category into Postgres.
- Without this, gameplay cannot start because there are not enough items.

### 4. (Optional) Load movies from TMDB
If you want the `movies` category:
1. Set `TMDB_API_KEY` in `backend/.env`
2. Recreate backend with the updated env:
```bash
docker compose up -d --build backend
```
3. Run ingestion:
```bash
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-movies 1000
```

Notes:
- Large ingests can take hours (for example, `--max-movies 50000`).
- Progress is checkpointed at `backend/data/tmdb_ingest_checkpoint.json`.
- If interrupted, rerun the same command to resume.

### 5. Open app
- Frontend dev URL: `http://localhost:5173`
- Backend API URL: `http://localhost:8015`

### 6. Stop services
```bash
docker compose down
```

To also remove Postgres data volume:
```bash
docker compose down -v
```

---

## Quick Start (Any OS)
```bash
docker compose up --build -d
docker compose exec backend python -m scripts.load_db
```

---

## Verify Data Is Loaded
Check categories endpoint in browser:
- `http://localhost:8015/api/game/categories`

Expected:
- `fountain_pens` should show a nonzero count (>= 50 needed to play).
- `movies` may be 0 unless TMDB ingestion was run.

---

## Game API Endpoints
| Method | Path | Description |
|---|---|---|
| GET | `/api/game/categories` | List supported categories and counts |
| POST | `/api/game/start` | Start a game session |
| GET | `/api/game/{game_id}/onboarding` | Get onboarding pool (50) |
| POST | `/api/game/{game_id}/onboarding/submit` | Submit 10 picks + set rating |
| POST | `/api/game/{game_id}/round/start` | Start next round (10 candidates) |
| POST | `/api/game/{game_id}/round/{round_number}/pick` | Submit round pick |
| GET | `/api/game/{game_id}/status` | Get game status/scores |
| GET | `/api/game/{game_id}/summary` | Get final game insights |
| GET | `/api/game/leaderboard` | Get leaderboard |
| GET | `/api/game/player/{player_name}/history` | Get player game history |

---

## Data / Utility Scripts
Run these from repo root:

| Script | Command | Purpose |
|---|---|---|
| Load pen dataset into Postgres-backed store | `docker compose exec backend python -m scripts.load_db` | Required for clone users to play |
| Ingest movies from TMDB | `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-movies 1000` | Optional movie category ingest |
| Category migration | `docker compose exec backend python -m scripts.migrate_multicategory_schema` | No-op placeholder in Postgres mode |
| Evaluate AI on completed games | `docker compose exec backend python -m scripts.evaluate_pbcf` | Prints accuracy/score metrics from completed games |

Warning:
- Some legacy migration scripts were previously included but are deprecated or removed. Do not run unknown migration scripts against production data.

## When To Run Data Scripts
- Run `docker compose exec backend python -m scripts.load_db`:
  - right after first `docker compose up --build -d` on a new machine
  - any time you reset volumes with `docker compose down -v`
  - any time `fountain_pens` count drops below 50
- Run `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-movies ...`:
  - only if you want the `movies` category enabled
  - again later if you want to ingest more movies
- Run `docker compose exec backend python -m scripts.migrate_multicategory_schema`:
  - only when importing old data that may miss the `category` field
  - usually not needed for fresh Docker-first setups

---

## Troubleshooting

### "Pens are not loading / pens not visible"
Cause:
- The local Postgres-backed store has no fountain pen docs.

Fix:
```bash
docker compose exec backend python -m scripts.load_db
```

### "Category disabled / ingest required"
Cause:
- Category has fewer than 50 items in the database.

Fix:
- For pens: run `docker compose exec backend python -m scripts.load_db`
- For movies: run `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-movies 50000`

### "Detected products without `category` field"
Fix:
```bash
docker compose exec backend python -m scripts.migrate_multicategory_schema
```

### Postgres connection error
Verify services are up with `docker compose ps`, then restart stack:
```bash
docker compose up -d --build
```

---

## License
Developed as part of CSC 492 (Senior Design coursework).
