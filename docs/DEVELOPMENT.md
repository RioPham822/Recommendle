# Development Guide

Technical reference for contributors working on Recommendle.
For clone-to-run setup, use the root `README.md`.

---

## 1. Current Capability Snapshot

### Implemented
- Mongo-first backend (`app.main`) with category-aware gameplay.
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
- Database: MongoDB

### Legacy compatibility
- The project is Mongo-first; legacy SQLite support has been removed from main documentation.

### Request flow (active mode)
1. React frontend calls `/api/game/*`.
2. FastAPI game routes in `backend/app/routes/game.py`.
3. Game logic in `backend/app/services/game_service.py`.
4. Model and feature-space logic in `backend/app/ml/prefix_cf.py`.
5. Data read/write through Mongo collections.

---

## 3. Data Model (MongoDB)

Primary collections:
- `products`
- `users`
- `sessions`
- `selections`
- `prefix_ratings`
- `games`
- `game_rounds`

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

### Legacy recommendation APIs (still present)
- `/api/products`
- `/api/users`
- `/api/sessions/*`
- `/api/debug/pbcf`

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
- Load pens into Mongo:
  - `python -m scripts.load_db`
  - Default target is MongoDB.

### Optional / advanced
- Ingest movies from TMDB:
  - `python -m scripts.ingest_movies_tmdb --max-movies 50000`
  - Uses checkpoint file: `backend/data/tmdb_ingest_checkpoint.json`
- Multi-category schema migration:
  - `python -m scripts.migrate_multicategory_schema`
- Model evaluation reports:
  - `python -m scripts.evaluate_pbcf`

---

## 7. Developer Workflows

### First run (fresh clone)
1. Install backend deps: `python -m pip install -r requirements.txt`
2. Copy env file from `.env.example` to `.env`.
3. Ensure MongoDB is running.
4. Load pens: `python -m scripts.load_db`
5. Start backend: `python -m uvicorn app.main:app --host localhost --port 8015 --reload`
6. In `frontend/`: `npm install && npm run dev`

### Reset and reload data safely
1. Drop relevant Mongo collections if needed.
2. Reload pens: `python -m scripts.load_db`
3. Optionally ingest movies again.

### Resume paused movie ingest
- Re-run same command:
  - `python -m scripts.ingest_movies_tmdb --max-movies 50000`
- Script resumes from checkpoint automatically.

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
- Mongo has no fountain pen docs yet.
Fix:
- Run `python -m scripts.load_db` (Mongo default).

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

### Mongo connection failure
Check:
- Mongo service is running.
- `MONGODB_URL` / `MONGODB_DB_NAME` in `backend/.env`.

---

## 10. Limitations and Next Priorities

### Current limitations
- No auth/user accounts for production identity.
- Recommendation quality depends on dataset size and quality.

### Recommended next steps
1. Add API integration tests for `/api/game/*`.
2. Add one-command bootstrap script for backend + frontend + data load.
3. Add automated DB health/data availability check in startup diagnostics.
4. Continue improving movie ingest completeness and operational docs.
