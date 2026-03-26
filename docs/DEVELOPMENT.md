# Development Guide

Technical reference for contributors working on Recommendle.
For clone-to-run setup, use the root `README.md`.

---

## 1. Current Capability Snapshot

### Implemented
- Postgres-first backend (`app.main`) with category-aware gameplay.
- Full fountain pen flow:
  - onboarding pool of 50
  - select exactly 10
  - set-level rating
  - 5 game rounds, 10 candidates per round
  - round scoring + final summary
- Movie category support (when ingested) via TMDB script.
- Hidden preference detection + hidden gem recommendations.
- Category-scoped leaderboard and player history.
- Light/dark mode UI and per-theme logo handling.
- Backend unit tests for category features and hidden preference behavior.

### In Progress / Optional
- Large-scale movie ingestion completion depends on valid TMDB key and runtime.

---

## 2. Runtime Architecture

### Active app path
- Backend entrypoint: `backend/app/main.py`
- Frontend dev server: Vite (`frontend`)
- Database: Postgres

### Legacy compatibility
- The project is Postgres-first; legacy SQLite support has been removed from main documentation.

### Request flow (active mode)
1. React frontend calls `/api/game/*`.
2. FastAPI game routes in `backend/app/routes/game.py`.
3. Game logic in `backend/app/services/game_service.py`.
4. Model and feature-space logic in `backend/app/ml/prefix_cf.py`.
5. Data read/write through Postgres tables.

---

## 3. Data Model (Postgres)

Primary tables:
- `products`
- `users`
- `games`
- `game_rounds`
- `prefix_ratings`

Category-aware product docs include `category` and `schema_version`.

Current categories:
- `fountain_pens`
- `movies`

Startup schema validation:
- `backend/app/services/schema_service.py` ensures required category fields/indexes exist.
- If products are missing `category`, startup fails and asks you to run migration.

---

## 4. API Surface (Current)

### Game APIs (primary)
- `GET /api/game/categories`
- `POST /api/game/start`
- `GET /api/game/{game_id}/onboarding`
- `POST /api/game/{game_id}/onboarding/submit`
- `POST /api/game/{game_id}/round/start`
- `POST /api/game/{game_id}/round/{round_number}/pick`
- `GET /api/game/{game_id}/status`
- `GET /api/game/{game_id}/summary`
- `GET /api/game/leaderboard`
- `GET /api/game/player/{player_name}/history`

### Additional APIs (still present)
- `/api/products`

---

## 5. ML / Recommendation Behavior

Core model:
- Prefix-based collaborative filtering with category-aware feature extraction.
- User vector updates after onboarding and each round pick.
- Round candidates combine high-likelihood and diversity picks.

Explainability:
- AI top candidate list and reason text per round.
- Learned preference/dislike features in final summary.

Hidden preference pipeline:
1. Compare learned feature weights vs selection frequency.
2. Detect latent features not explicitly targeted.
3. Generate hidden gem recommendations from latent dimensions.

---

## 6. Script Catalog (What to Run and Why)

Run all commands below from `backend/` unless noted.

### Required for normal clone setup
- Load pens into Postgres:
  - `python -m scripts.load_db`
  - Default target is Postgres.

### Optional / advanced
- Ingest movies from TMDB:
  - `python -m scripts.ingest_movies_tmdb --max-candidates 30000 --max-rps 8 --no-resume`
  - `--max-movies` is optional; if omitted, all quality-passing candidates are upserted
  - if set, `--max-movies` becomes a final selected/upserted cap
  - `--max-candidates` controls candidate pool breadth and runtime
  - `--max-pages-per-lane` controls pagination depth per lane query
  - `--max-rps` controls request pacing; retry/backoff is built in for 429/network issues
  - `--lane-bars` shows grouped live lane progress bars in interactive terminals
  - Uses checkpoint file: `backend/data/tmdb_ingest_checkpoint.json`
- Ingest games from IGDB:
  - `python -m scripts.ingest_games_igdb --max-candidates 5000`
  - `--max-games` is optional; if omitted, all quality-passing candidates are upserted
  - if set, `--max-games` becomes a final selected/upserted cap
  - `--max-candidates` controls candidate pool breadth and runtime
  - `--max-pages-per-lane` controls pagination depth per lane query
  - `--max-rps` controls request pacing; retry/backoff is built in for 429/network issues
  - Uses checkpoint file: `backend/data/igdb_ingest_checkpoint.json`
- Multi-category schema migration:
  - `python -m scripts.migrate_multicategory_schema`
- Model evaluation reports:
  - `python -m scripts.evaluate_pbcf`

### Ingestion strategy summary
For the full operational version (including Docker-first commands and VM background-run examples), see `README.md`:
- `README.md` -> `Ingestion Strategy (TMDB + IGDB)`

- TMDB lane-based candidate pool:
  - `trending_day`, `trending_week`
  - per-year `discover_popularity`, `discover_vote_count`, `discover_long_tail`
  - `discover_diversity` lanes (language+decade and genre variants)
  - `discover_classics`
- TMDB hard quality filters:
  - release date must not be in the future
  - runtime >= 60 minutes
  - poster required
  - at least one genre
  - `vote_count >= --min-vote-count`
- TMDB final selection:
  - quality score ranking on quality-passing docs
  - optional `--max-movies` cap applies diversity balancing by decade/genre/language (with classics quota)
- IGDB candidate lanes:
  - `popular_hype`, `popular_rating_count`, `high_rated`, `recent_hype`
  - `long_tail_quality`, `decade_balance`, `classics`
- IGDB hard quality filters:
  - release date must not be in the future
  - cover required
  - at least one genre and one platform
  - `total_rating_count >= --min-rating-count`
  - `total_rating >= --min-total-rating`
- IGDB final selection:
  - quality score (total rating, rating count, hypes, recency) + diversity balancing by decade/genre/platform
  - optional `--max-games` cap after filtering

---

## 7. Developer Workflows

### First run (fresh clone)
1. Install backend deps: `python -m pip install -r requirements.txt`
2. Copy env file from `.env.example` to `.env`.
3. Ensure Postgres is running.
4. Load pens: `python -m scripts.load_db`
5. Start backend: `python -m uvicorn app.main:app --host localhost --port 8015 --reload`
6. In `frontend/`: `npm install && npm run dev`

### Reset and reload data safely
1. Drop relevant Postgres collections if needed.
2. Reload pens: `python -m scripts.load_db`
3. Optionally ingest movies again.

### Resume paused movie ingest
- Re-run same command:
  - `python -m scripts.ingest_movies_tmdb --max-candidates 30000 --max-rps 8`
- Script resumes from checkpoint automatically.
- If you want a fresh pool (different target/strategy), include `--no-resume`.

---

## 8. Testing and Validation

### Backend unit tests
```bash
cd backend
python -m unittest discover -s tests -v
```

### Backend compile sanity
```bash
cd backend
python -m compileall app scripts tests
```

### Frontend build verification
```bash
cd frontend
npm run build
```

### API smoke script
```bash
bash test_game_api.sh
```

Note:
- The smoke script assumes backend is running on port `8015`.

---

## 9. Common Issues

### Pens not visible after clone
Cause:
- Postgres has no fountain pen docs yet.
Fix:
- Run `python -m scripts.load_db` (Postgres default).

### Movie category disabled / ingest required
Cause:
- Fewer than 50 movie products loaded.
Fix:
- Complete TMDB ingest or seed enough movie docs.

### Startup error about missing `category`
Cause:
- Old product docs without schema/category fields.
Fix:
- Run `python -m scripts.migrate_multicategory_schema`.

### Postgres connection failure
Check:
- Postgres service is running.
- `DATABASE_URL` in `backend/.env`.

---

## 10. Limitations and Next Priorities

### Current limitations
- Recommendation quality depends on dataset size and quality.

### Recommended next steps
1. Add API integration tests for `/api/game/*`.
2. Add one-command bootstrap script for backend + frontend + data load.
3. Add automated DB health/data availability check in startup diagnostics.
4. Continue improving movie ingest completeness and operational docs.
