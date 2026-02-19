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
- Uses **MongoDB** as the active backend for the app (`app.main_mongo`).
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

## Tech Stack
- Frontend: React 18 + Vite + CSS
- Backend: FastAPI + Uvicorn (Python)
- Database: MongoDB (Motor/PyMongo)
- Model: Prefix-based collaborative filtering with sequential updates

## Repository Layout
```text
backend/
  app/
    main_mongo.py              # Active FastAPI app (MongoDB)
    routes/game.py             # Game API endpoints
    services/game_service.py   # Core game logic
    ml/prefix_cf.py            # Preference model + hidden preference logic
  data/
    products.json              # Fountain pen catalog in repo
  scripts/
    load_db.py                 # Loads fountain pens into MongoDB (default)
    ingest_movies_tmdb.py      # Ingests movies into MongoDB from TMDB
    migrate_multicategory_schema.py
    migrate_to_mongo.py
frontend/
  src/
start.bat                      # Convenience launcher (Windows)
```

## Prerequisites
- Python 3.10+
- Node.js 18+ and npm
- MongoDB running locally (default `mongodb://localhost:27017`)

---

## Setup From Clone (Exact Steps)

### 1. Clone
```bash
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git
cd 2026Spring-Team42-Decidio-3
```

### 2. Backend install
```bash
cd backend
python -m pip install -r requirements.txt
```

### 3. Create backend env file
PowerShell:
```powershell
Copy-Item .env.example .env
```

Bash:
```bash
cp .env.example .env
```

Default values in `.env.example`:
```env
MONGODB_URL=mongodb://localhost:27017
MONGODB_DB_NAME=decidio
MONGODB_MAX_POOL_SIZE=10
MONGODB_MIN_POOL_SIZE=1
TMDB_API_KEY=
```

### 4. Load the fountain pen dataset into MongoDB (required)
From `backend/`:
```bash
python -m scripts.load_db
```

Important:
- `scripts.load_db` now targets **MongoDB by default**.
- This is required for clone users; otherwise the game will have no pen data in Mongo.

### 5. (Optional) Load movies into MongoDB
If you want movie gameplay too:
1. Set `TMDB_API_KEY` in `backend/.env`
2. Run:
```bash
python -m scripts.ingest_movies_tmdb --max-movies 1000 
```
Note: ()

Notes:
- This can run for a long time. The deal amount is 50000 movies but it takes multiple hours to ingest
- Progress is checkpointed at `backend/data/tmdb_ingest_checkpoint.json`.
- If stopped, rerun the same command and it resumes from checkpoint.

### 6. Start backend API
From `backend/`:
```bash
python -m uvicorn app.main_mongo:app --host localhost --port 8015 --reload
```

### 7. Start frontend
In a new terminal:
```bash
cd frontend
npm install
npm run dev
```

### 8. Open app
- Frontend dev URL: `http://localhost:5173`
- Backend API URL: `http://localhost:8015`

---

## Quick Start (Windows)
After dependencies are installed and pens are loaded once, you can use:
```bat
start.bat
```
This launches backend and frontend in separate windows.

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
Run these from `backend/`:

| Script | Command | Purpose |
|---|---|---|
| Load pen dataset into MongoDB | `python -m scripts.load_db` | Required for clone users to play pens |
| Legacy SQLite load | `python -m scripts.load_db --target sqlite` | Old backend compatibility |
| Ingest movies from TMDB | `python -m scripts.ingest_movies_tmdb --max-movies 50000` | Optional movie category |
| Multi-category schema migration | `python -m scripts.migrate_multicategory_schema` | Fix old docs missing `category` |
| SQLite -> Mongo migration | `python -m scripts.migrate_to_mongo` | Migrates legacy DB (destructive to Mongo collections) |
| Evaluate AI on completed games | `python -m scripts.evaluate_pbcf` | Generates performance reports |

Warning for `migrate_to_mongo.py`:
- It drops and rewrites key Mongo collections. Do not run it on a DB you need to preserve without backup.

---

## Troubleshooting

### "Pens are not loading / pens not visible"
Cause:
- MongoDB has no fountain pen docs.

Fix:
```bash
cd backend
python -m scripts.load_db
```

### "Category disabled / ingest required"
Cause:
- Category has fewer than 50 items in Mongo.

Fix:
- For pens: run `python -m scripts.load_db`
- For movies: run `python -m scripts.ingest_movies_tmdb --max-movies 50000`

### "Detected products without `category` field"
Fix:
```bash
cd backend
python -m scripts.migrate_multicategory_schema
```

### MongoDB connection error
Verify MongoDB is running and `.env` has correct `MONGODB_URL`.

---

## License
Developed as part of CSC 492 (Senior Design coursework).
