# Recommendle

Recommendle is an interactive web game where a human player competes against an AI recommendation model.  
It is a CSC 492 Senior Design project focused on **sequential preference modeling**: learning user taste from a sequence of choices instead of one-off ratings.

Live website: https://recommendle-frontend.onrender.com

## What The Program Currently Does
- Runs a web game with:
  - onboarding: select 10 items from a pool of 50
  - 5 gameplay rounds with 10 candidates per round
  - AI-vs-human scoring each round
  - final summary with explainability and recommendations
- Supports category-aware gameplay:
  - `fountain_pens` (included in repo and loadable immediately)
  - `movies` (loadable via TMDB ingestion script)
  - `games` (loadable via IGDB ingestion script)
- Uses **Postgres** as the active backend for the app (`app.main`).
- Provides two exploration modes in UI:
  - visual mode
  - feature mode
- Tracks leaderboard and player history by category.
- Detects hidden/latent preference patterns and surfaces "hidden gems."
- Supports account-based play with username/password authentication:
  - registration and login endpoints
  - session tokens with expiry tracking
  - user accounts with independent play history
- Includes local maintenance utilities in `backend/test.py`:
  - database summaries and cleanup commands
  - movie export to JSON or Excel-friendly spreadsheet via `export-movies-json` / `export-movies-excel`

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
    routes/auth.py             # Auth API endpoints
    services/game_service.py   # Core game logic
    services/auth.py           # User/session auth logic
    ml/prefix_cf.py            # Preference model + hidden preference logic
  data/
    products.json              # Fountain pen catalog in repo
  scripts/
    load_db.py                 # Loads fountain pens into Postgres-backed store
    ingest_movies_tmdb.py      # Ingests movies from TMDB into Postgres
    ingest_games_igdb.py       # Ingests games from IGDB into Postgres
    migrate_multicategory_schema.py
frontend/
  src/
start.bat                      # Convenience launcher (Windows)
```

`start.bat` starts `postgres`, `backend`, seeds the fountain pen dataset, and then starts the optional local frontend container.

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

### 2. Start backend services (Postgres + backend)
From repo root:
```bash
docker compose up --build -d postgres backend
```

### 2b. (Optional) Start local frontend container
If you want the frontend in Docker for local testing:
```bash
docker compose --profile local-frontend up -d --build frontend
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
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
```

Notes:
- `--max-movies` is optional. If omitted, all quality-passing candidates are upserted.
- If provided, `--max-movies` is the final cap after filtering/diversity balancing.
- Candidate fetch volume is controlled by `--max-candidates` (higher = broader but slower).
- `--max-pages-per-lane` controls pagination depth per lane query during candidate discovery.
- Request pacing is controlled by `--max-rps` and includes 429/network backoff handling.
- For a new target/strategy, use `--no-resume` (otherwise checkpoint data is reused).
- Progress is checkpointed at `backend/data/tmdb_ingest_checkpoint.json`.
- If interrupted, rerun the same command to resume.

### 4b. (Optional) Load games from IGDB
If you want the `games` category:
1. Set `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` in `backend/.env`
2. Recreate backend with the updated env:
```bash
docker compose up -d --build backend
```
3. Run ingestion:
```bash
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
```

Notes:
- `--max-games` is optional. If omitted, all quality-passing candidates are upserted.
- If provided, `--max-games` is the final cap after filtering/diversity balancing.
- Candidate fetch volume is controlled by `--max-candidates` (higher = broader but slower).
- `--max-pages-per-lane` controls pagination depth per IGDB lane query (higher can increase total unique candidates).
- Progress is checkpointed at `backend/data/igdb_ingest_checkpoint.json`.
- If interrupted, rerun the same command to resume.

### 5. Open app
- Local frontend (if profile enabled): `http://localhost:5173`
- Local backend API: `http://localhost:8015`
- Public backend (recommended for hosted frontend): `https://<your-vm-domain>`

For VM + Nginx deployment details, see [NGINX_SETUP.md](docs/NGINX_SETUP.md).

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
docker compose up --build -d postgres backend
docker compose exec backend python -m scripts.load_db
```

Local frontend (optional):
```bash
docker compose --profile local-frontend up -d --build frontend
```

---

## Verify Data Is Loaded
Check categories endpoint in browser:
- `http://localhost:8015/api/game/categories`

Expected:
- `fountain_pens` should show a nonzero count (>= 50 needed to play).
- `movies` may be 0 unless TMDB ingestion was run.
- `games` may be 0 unless IGDB ingestion was run.

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
| GET | `/api/game/resume-state` | Check whether a player has an in-progress game |

## Auth API Endpoints
| Method | Path | Description |
|---|---|---|
| POST | `/api/auth/register` | Register a user and return a session token |
| POST | `/api/auth/login` | Login and return a session token |
| GET | `/api/auth/user/{user_id}` | Get account profile details |
| POST | `/api/auth/change-password` | Change password for a user |
| POST | `/api/auth/logout` | Invalidate a session token |

---

## Data / Utility Scripts
Run these from repo root:

| Script | Command | Purpose |
|---|---|---|
| Load pen dataset into Postgres-backed store | `docker compose exec backend python -m scripts.load_db` | Required for clone users to play |
| Ingest movies from TMDB | `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8` | Optional movie category ingest |
| Ingest games from IGDB | `docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000` | Optional games category ingest |
| Backend DB utility (`backend/test.py`) | `docker compose exec backend python test.py summary` | Quick DB summary and maintenance commands |
| Export movies to JSON | `docker compose exec backend python test.py export-movies-json --output data/movies_export.json` | Writes a JSON export of movie records |
| Export movies to Excel | `docker compose exec backend python test.py export-movies-excel --output data/movies_export.csv` | Writes an Excel-friendly CSV with every discovered movie field as a column |
| Category migration | `docker compose exec backend python -m scripts.migrate_multicategory_schema` | No-op placeholder in Postgres mode |
| Evaluate AI on completed games | `docker compose exec backend python -m scripts.evaluate_pbcf` | Prints accuracy/score metrics from completed games |

Warning:
- Some legacy migration scripts were previously included but are deprecated or removed. Do not run unknown migration scripts against production data.

`backend/test.py` examples (from repo root):
- `docker compose exec backend python test.py summary`
- `docker compose exec backend python test.py list-collections`
- `docker compose exec backend python test.py clear-games`
- `docker compose exec backend python test.py clear-products --category movies`
- `docker compose exec backend python test.py export-movies-json --output data/movies_export.json`
- `docker compose exec backend python test.py export-movies-excel --output data/movies_export.csv`

## Ingestion Strategy (TMDB + IGDB)
This section explains how candidate items are fetched before upsert.

### TMDB movie ingest (`scripts.ingest_movies_tmdb`)
- Candidate discovery uses round-robin pagination across multiple lanes until `--max-candidates` is reached (or lanes are exhausted):
  - `trending_day`, `trending_week`
  - `discover_popularity` (per-year, `sort_by=popularity.desc`)
  - `discover_vote_count` (per-year, `sort_by=vote_count.desc`, `vote_count.gte=50`)
  - `discover_long_tail` (per-year, `vote_count` between 20 and 400, `vote_average.gte=5.5`)
  - `discover_diversity` (language+decade lanes and genre lanes, generally `vote_count.gte=20`)
  - `discover_classics` (`release_date <= 2000-12-31`, `vote_average.gte=7.5`, `vote_count.gte=5000`)
- Hard quality filters (applied after details fetch):
  - released (not future date)
  - runtime >= 60 minutes
  - has poster
  - at least one genre
  - `vote_count >= --min-vote-count` (default 20)
- Soft ranking + diversity:
  - quality score combines vote count, vote average, popularity, recency
  - if `--max-movies` is set, final selection uses diversity balancing across decade/genre/language
  - includes a classic-movie quota when diversity selection is applied
- Progress and resume:
  - checkpoint: `backend/data/tmdb_ingest_checkpoint.json`
  - interactive multi-bars available with `--lane-bars`
  - `--no-resume` forces fresh candidate discovery

### IGDB game ingest (`scripts.ingest_games_igdb`)
- Candidate discovery builds a deduplicated pool from lane queries (IGDB APICalypse), including:
  - `popular_hype`
  - `popular_rating_count`
  - `high_rated`
  - `recent_hype`
  - `long_tail_quality`
  - `decade_balance` (per-decade lane)
  - `classics` (released on/before 2005-12-31, strong rating thresholds)
- Base constraints for most lanes:
  - `version_parent = null`
  - non-null release date within `[--start-year, --end-year]` and not future-dated
  - category in `(0,4,8,9,10,11)` (main game-like categories)
- Hard quality filters (after details fetch):
  - released (not future date)
  - has cover
  - at least one genre and one platform
  - `total_rating_count >= --min-rating-count` (default 20)
  - `total_rating >= --min-total-rating` (default 60.0)
- Soft ranking + diversity:
  - quality score combines total rating, rating count, hypes, recency
  - if `--max-games` is set, final selection uses diversity balancing across decade/genre/platform and a classics quota
- Progress and resume:
  - checkpoint: `backend/data/igdb_ingest_checkpoint.json`
  - `--no-resume` forces fresh candidate discovery

### Run long jobs in background (Ubuntu VM)
If an ingest command may run for hours, run it with `nohup` and disable TTY allocation:

```bash
nohup docker compose exec -T backend python -m scripts.ingest_movies_tmdb --max-candidates 30000 --max-rps 8 > backend/data/ingest_movies.log 2>&1 &
echo $! > backend/data/ingest_movies.pid
```

View logs while detached:
```bash
tail -f backend/data/ingest_movies.log
```

Check process:
```bash
ps -fp "$(cat backend/data/ingest_movies.pid)"
```

Stop process:
```bash
kill "$(cat backend/data/ingest_movies.pid)"
```

Notes:
- `2>&1` captures both normal output and errors in the same log file.
- `tqdm` output is still logged, but in non-interactive mode it may appear as periodic text updates instead of a single animated line.

## When To Run Data Scripts
- Run `docker compose exec backend python -m scripts.load_db`:
  - right after first `docker compose up --build -d postgres backend` on a new machine
  - any time you reset volumes with `docker compose down -v`
  - any time `fountain_pens` count drops below 50
- Run `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates ...`:
  - only if you want the `movies` category enabled
  - again later if you want to ingest more movies
  - use `--no-resume` when changing target size or ingest strategy
- Run `docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates ...`:
  - only if you want the `games` category enabled
  - again later if you want to ingest more games
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
- For movies: run `docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 30000 --max-rps 8 --no-resume`
- For games: run `docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 50000`

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
