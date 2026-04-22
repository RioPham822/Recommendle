# Developer's Guide

This guide is for sponsors or future senior design teams who want to run, maintain, extend, or integrate with Recommendle. It focuses on practical development tasks rather than final-report background.

Recommendle is a React/FastAPI/Postgres application where a player trains an AI recommender through onboarding selections, round choices, negative feedback, and optional persona starting profiles.

## 1. Technology Stack

- Frontend: React 18, Vite, Material UI
- Backend: FastAPI, SQLAlchemy async ORM, Pydantic
- Database: Postgres
- Runtime: Docker Compose
- Recommendation model: prefix-based collaborative filtering with category-aware feature extraction

## 2. Repository Map

Important directories and files:

- `backend/app/main.py`: FastAPI app entrypoint, CORS, route registration, startup initialization
- `backend/app/db.py`: environment settings, SQLAlchemy models, async database engine/session setup
- `backend/app/routes/`: HTTP route modules
- `backend/app/routes/game.py`: game, onboarding, round, leaderboard, persona-start routes
- `backend/app/routes/admin.py`: admin user, catalog, ML config, and persona simulation routes
- `backend/app/routes/auth.py`: registration, login, logout, password routes
- `backend/app/services/`: backend business logic
- `backend/app/services/game_service.py`: core game service facade
- `backend/app/services/game_play.py`: onboarding and round lifecycle behavior
- `backend/app/services/game_insights.py`: status, summary, leaderboard, and insight behavior
- `backend/app/services/recommender.py`: model refresh and recommendation service
- `backend/app/services/persona_simulation.py`: admin persona simulation and playable persona profile refresh
- `backend/app/category_profiles.py`: category metadata, fields, labels, and feature token helpers
- `backend/app/personas.py`: bundled persona definitions
- `backend/scripts/`: data loading, ingestion, migration, and evaluation scripts
- `backend/tests/`: backend unit and model tests
- `frontend/src/App.jsx`: top-level frontend state and screen flow
- `frontend/src/lib/api.js`: frontend API client and auth header handling
- `frontend/src/components/`: React UI components
- `frontend/src/styles.css`: main application styling
- `docker-compose.yml`: local Docker orchestration
- `docs/API_REFERENCE.md`: REST API route reference
- `docs/ADDING_DATASETS.md`: category extension reference
- `docs/INGESTION_GUIDE.md`: movie/game ingestion details

## 3. Development Prerequisites

These commands assume Windows with PowerShell, because the current project workspace is Windows-based. The Docker workflow is the preferred setup because it avoids local Postgres differences.

Install:

- Git
- Docker Desktop with Docker Compose
- Python 3.12
- Node.js 20 or newer

Verify tools:

```powershell
git --version
docker --version
docker compose version
python --version
node --version
npm --version
```

Clone the repository:

```powershell
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git
cd 2026Spring-Team42-Decidio-3
```

Create backend environment file:

```powershell
Copy-Item backend\.env.example backend\.env
```

For Docker development, the compose file injects the container database URL. Keep `backend/.env` for optional API keys and local non-Docker use.

Optional API keys:

```env
TMDB_API_KEY=
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
```

Use these only if you need to ingest movies or games from external APIs.

## 4. Run From A Checkout

### Docker-first workflow

Start Postgres and backend:

```powershell
docker compose up --build -d postgres backend
```

Load bundled fountain pen data:

```powershell
docker compose exec backend python -m scripts.load_db
```

Start the local frontend container:

```powershell
docker compose --profile local-frontend up -d --build frontend
```

Open:

- Frontend: `http://localhost:5173`
- Backend API: `http://localhost:8015`

Verify backend:

```powershell
curl http://localhost:8015/api/game/categories
```

Stop services:

```powershell
docker compose down
```

Stop services and remove the local database volume:

```powershell
docker compose down -v
```

### Non-Docker backend and frontend workflow

Use this if you already have Postgres running locally.

Backend:

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python -m uvicorn app.main:app --host localhost --port 8015 --reload
```

Frontend:

```powershell
cd frontend
npm install
npm run dev
```

For non-Docker backend use, set `DATABASE_URL` in `backend/.env`, for example:

```env
DATABASE_URL=postgresql+asyncpg://decidio:decidio_pass@localhost:5432/decidio
```

## 5. Build Commands

Backend Docker image:

```powershell
docker compose build backend
```

Frontend production build:

```powershell
cd frontend
npm ci
npm run build
```

Backend compile sanity:

```powershell
cd backend
python -m compileall app scripts tests
```

These are the build artifacts used by deployment:
- backend Docker image from `backend/Dockerfile`
- frontend static files in `frontend/dist/`

## 6. Running Tests

Install backend dependencies first if running outside Docker:

```powershell
cd backend
python -m pip install -r requirements.txt
```

Run all backend tests:

```powershell
cd backend
python -m unittest discover -s tests -v
```

Run a focused test file:

```powershell
cd backend
python -m unittest tests.services.test_game_play -v
```

Run compile sanity:

```powershell
cd backend
python -m compileall app scripts tests
```

Run frontend production build check:

```powershell
cd frontend
npm run build
```

Optional live database validation requires a running Postgres database and suitable data. See `backend/tests/ml/test_model_validation_db.py`.

## 7. Data And Ingestion Workflows

Load bundled fountain pen data:

```powershell
docker compose exec backend python -m scripts.load_db
```

Ingest movies from TMDB:

```powershell
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
```

Ingest games from IGDB:

```powershell
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
```

Inspect database summary:

```powershell
docker compose exec backend python test.py summary
```

Export movie records:

```powershell
docker compose exec backend python test.py export-movies-excel --output data/movies_export.csv
```

See `docs/INGESTION_GUIDE.md` for detailed ingestion flags and checkpoint behavior.

## 8. Backend Design Overview

### Request flow

1. React calls functions in `frontend/src/lib/api.js`.
2. API client sends requests to FastAPI.
3. FastAPI route modules validate request/response schemas.
4. Route handlers call service classes.
5. Services read/write SQLAlchemy ORM records.
6. The recommender refreshes from stored products and completed interactions.

### Database models

Main SQLAlchemy ORM models live in `backend/app/db.py`.

Important tables:

- `products`: category id plus JSON product payload
- `users`: accounts, roles, session tokens
- `games`: game sessions and model state
- `game_rounds`: round-level choices and AI results
- `prefix_ratings`: onboarding prefix-rating feedback for model training
- `persona_simulation_runs`: admin persona run state and event timeline
- `persona_profiles`: latest completed playable profile for each persona

The project does not currently use Alembic migrations. Startup helpers in `db.py` and `schema_service.py` create or align required database structures. If the schema grows significantly, adding Alembic would be a good future improvement.

### Recommendation model

Start with:

- `backend/app/ml/prefix_cf.py`
- `backend/app/services/recommender.py`
- `backend/app/category_profiles.py`

The category profile controls which product fields become features. Product data stays flexible because category-specific payloads live in JSON.

### Persona system

Start with:

- `backend/app/personas.py`
- `backend/app/services/persona_simulation.py`
- `backend/app/routes/admin.py`
- `backend/app/routes/game.py`

Admin simulations generate canonical persona profiles. Public players can start from those completed profiles and skip onboarding.

## 9. Frontend Design Overview

Main screen flow lives in `frontend/src/App.jsx`.

Important components:

- `AuthScreen.jsx`: login/register UI
- `WelcomeScreen.jsx`: category selection, resume/start, persona starts, leaderboard
- `BetaSeedScreen.jsx`: optional quick likes/dislikes before onboarding
- `OnboardingGrid.jsx`: 100-item onboarding selection grid
- `SetRatingModal.jsx`: onboarding rating step
- `RoundArena.jsx`: active round candidate selection
- `RoundResultPanel.jsx`: AI-vs-human result and explanation
- `FinalSummary.jsx`: completed-run summary and recommendations
- `AdminScreen.jsx`: admin products, users, personas, and ML settings
- `ProductCard.jsx`: reusable product card
- `PreferenceDeck.jsx`: active preference deck

API calls should be added to `frontend/src/lib/api.js` first, then used by components.

## 10. REST API Conventions

Full route list: `docs/API_REFERENCE.md`.

Base URL in local development:

```text
http://localhost:8015
```

Authentication headers for protected routes:

```text
Authorization: Bearer <session_token>
X-User-Id: <user_id>
```

Frontend stores these in `localStorage` and sends them through `getAuthHeaders()` in `frontend/src/lib/api.js`.

Common response convention:
- success responses are JSON
- errors use HTTP status codes and usually include `detail`

Admin product query conventions:
- `category` is required
- `search` is optional
- `filters` is JSON encoded in a query parameter
- `limit` and `offset` handle pagination
- `sort_field` and `sort_dir` control sorting

Example login:

```powershell
curl -X POST http://localhost:8015/api/auth/login `
  -H "Content-Type: application/json" `
  -d "{\"username\":\"alice\",\"password\":\"MyPassword123\"}"
```

Example start game:

```powershell
curl -X POST http://localhost:8015/api/game/start `
  -H "Content-Type: application/json" `
  -d "{\"player_name\":\"Alice\",\"category\":\"movies\",\"mode\":\"beta\",\"fresh_start\":true}"
```

Example admin product query:

```powershell
curl "http://localhost:8015/api/admin/products?category=movies&limit=100&offset=0&sort_field=title&sort_dir=asc" `
  -H "Authorization: Bearer <session_token>" `
  -H "X-User-Id: <user_id>"
```

## 11. Common Extension Tasks

### Add a new REST API route

1. Choose the route module:
   - game behavior: `backend/app/routes/game.py`
   - admin behavior: `backend/app/routes/admin.py`
   - auth behavior: `backend/app/routes/auth.py`
2. Add request and response schemas in a schema module, such as `schemas_game.py`, if the payload is structured.
3. Implement business logic in a service under `backend/app/services/`.
4. Add the route handler and call the service.
5. Add frontend API helper in `frontend/src/lib/api.js` if the UI needs it.
6. Add or update tests under `backend/tests/`.

Minimal FastAPI pattern:

```python
@router.get("/example")
async def get_example(db: AsyncSession = Depends(get_db)):
    return await example_service.load_example(db)
```

For admin routes, require admin access:

```python
@router.get("/example")
async def get_admin_example(_: UserRecord = Depends(require_admin)):
    return {"ok": True}
```

### Add a new database table

1. Add a SQLAlchemy model in `backend/app/db.py`.
2. Include sensible defaults and indexes.
3. Update startup compatibility helpers if existing databases need to be altered.
4. Add service functions that read/write the table.
5. Add tests for model conversion, service behavior, and route behavior.

Because there is no Alembic migration layer yet, be careful when changing existing columns. Prefer additive changes and startup-safe compatibility SQL.

### Add a new frontend screen

1. Create a component under `frontend/src/components/`.
2. Add API helpers in `frontend/src/lib/api.js`.
3. Add state and navigation in `frontend/src/App.jsx`.
4. Add styling in `frontend/src/styles.css` or a component CSS file if the pattern already exists.
5. Run `npm run build`.

Keep screens task-focused. The app currently uses screen components rather than a route library.

### Add a new product category

1. Pick a stable category id, such as `books`.
2. Add a `CategoryProfile` in `backend/app/category_profiles.py`.
3. Normalize product payload fields.
4. Add or adapt an ingestion script in `backend/scripts/`.
5. Store rows in `products` with `category=<category_id>` and JSON payload in `data`.
6. Verify `GET /api/game/categories`.
7. Confirm onboarding, rounds, summaries, and admin product views work.
8. Add tests for category profile behavior and product consistency.

The frontend currently treats a category as ready when it has at least 100 visible items.

### Add or update personas

1. Edit `backend/app/personas.py`.
2. Add a unique `id`, `category`, `display_name`, `summary`, likes, dislikes, and behavior values.
3. Restart the backend.
4. Use Admin -> `Persona Library` to launch the persona.
5. Use Admin -> `Persona Stats` to confirm the run completes.
6. Confirm the persona appears on the public welcome screen for that category.

Persona preferences should use product fields that exist in that category's payload.

### Tune recommendation behavior

Use Admin -> `ML Settings` for runtime parameter changes.

For code-level changes, start with:

- `backend/app/ml/prefix_cf.py`
- `backend/app/services/recommender.py`
- `backend/app/services/game_play.py`
- `backend/tests/ml/`

After changing model behavior, run:

```powershell
cd backend
python -m unittest discover -s tests -v
python -m compileall app scripts tests
```

Also run the frontend build if API payloads changed:

```powershell
cd frontend
npm run build
```

## 12. Testing Guidance For Changes

Use focused tests while developing, then run the full suite before handoff.

Recommended coverage by change type:

- API route change: route tests under `backend/tests/api/`
- gameplay change: service tests under `backend/tests/services/`
- category profile change: core tests under `backend/tests/core/`
- recommender/model change: model tests under `backend/tests/ml/`
- frontend API payload change: `npm run build` and manual browser smoke test

Manual smoke test after major changes:

1. Start Docker services.
2. Load at least one dataset.
3. Register or log in.
4. Select a ready category.
5. Complete onboarding.
6. Play at least one round.
7. Confirm final summary still loads when a run completes.
8. For admin changes, log in as admin and verify the relevant tab.

## 13. Debugging Tips

Backend logs:

```powershell
docker compose logs --tail=100 backend
```

Postgres logs:

```powershell
docker compose logs --tail=100 postgres
```

Check running containers:

```powershell
docker compose ps
```

Check local API:

```powershell
curl http://localhost:8015/api/game/categories
```

Common issues:

- Backend cannot connect to Postgres: verify `DATABASE_URL` and that Postgres is healthy.
- Category not ready: load enough data and confirm visible count is at least 100.
- CORS error: add the frontend origin to `allowed_origins` in `backend/app/main.py`.
- Frontend calls wrong backend: set `VITE_API_BASE_URL` before building or starting Vite.
- Persona does not appear publicly: run a successful admin persona simulation first.

## 14. Documentation To Keep Updated

Update these docs when changing behavior:

- `docs/API_REFERENCE.md`: route additions or payload changes
- `docs/FEATURES_GUIDE.md`: user-visible behavior changes
- `docs/ADDING_DATASETS.md`: category extension changes
- `docs/INGESTION_GUIDE.md`: ingestion script flag or workflow changes
- `docs/sdc_docs/DEPLOYMENT_GUIDE.md`: production setup changes
- `docs/sdc_docs/USER_MANUAL.md`: user workflow changes
- `docs/sdc_docs/DEVELOPERS_GUIDE.md`: developer setup or extension changes
