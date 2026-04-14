# Features Guide

This guide summarizes the user-facing behavior implemented in the current app.

## Authentication

Implemented behavior:
- users can register and log in
- sessions use expiring tokens
- each account keeps separate play history
- the first registered account becomes an admin unless a bootstrap admin already exists

Main endpoints:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/user/{user_id}`
- `POST /api/auth/logout`

## Categories

Current categories:
- `fountain_pens`
- `movies`
- `games`

Frontend readiness rule:
- the welcome screen currently treats a category as ready when it has at least 100 visible items

## Gameplay Flow

Current frontend flow:
1. The player signs in.
2. The player selects a category.
3. The frontend starts a `beta` game session.
4. The player can optionally seed likes and dislikes before onboarding.
5. The player completes onboarding from a 100-item pool.
6. The player rates the onboarding set.
7. The player plays AI-vs-human rounds until the model reaches the configured preference-match streak target.
8. The player sees a final summary and leaderboard context.

Current rules:
- onboarding pool size: 100 items
- onboarding selections allowed: 1 to 10
- round candidates: 10
- default preference-match streak target: 5
- the run can finish in more than 5 rounds if the AI does not keep its streak alive

## Beta Features

Currently implemented:
- preference seeding before onboarding
- negative feedback through "less like this"
- round refresh after negative feedback
- editable preference deck during active play

Relevant endpoints:
- `POST /api/game/{game_id}/seed`
- `POST /api/game/{game_id}/feedback`
- `POST /api/game/{game_id}/onboarding/refresh`
- `POST /api/game/{game_id}/round/refresh`
- `PATCH /api/game/{game_id}/preferences`

## Explainability

The app currently exposes:
- AI-vs-human round results
- per-round AI explanation payloads
- hidden preference hints
- final learned preference summary
- hidden-gem recommendations

## Leaderboards And History

Implemented:
- category-scoped leaderboard
- per-player history by category
- resume-state lookup for unfinished runs

Relevant endpoints:
- `GET /api/game/leaderboard`
- `GET /api/game/player/{player_name}/history`
- `GET /api/game/resume-state`

## Admin Features

Admin capabilities exposed by the backend and frontend:
- inspect current admin identity
- list users
- inspect per-user ML stats
- clear a user's progress
- delete a user
- inspect and export category product catalogs
- view and update ML config values

## Data Utilities

Common commands:

```bash
docker compose exec backend python -m scripts.load_db
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
docker compose exec backend python test.py summary
docker compose exec backend python test.py clear-products --category movies
docker compose exec backend python test.py export-movies-excel --output data/movies_export.csv
```

## Frontend Runtime Config

The frontend reads its API base URL from `VITE_API_BASE_URL`.

Compose default:

```yaml
VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8015}
```
