# Features Guide

This file summarizes currently implemented features and how to use them.

## 1. User Authentication

Implemented endpoints:
- `POST /api/auth/register`
- `POST /api/auth/login`
- `GET /api/auth/user/{user_id}`
- `POST /api/auth/change-password?user_id=...`
- `POST /api/auth/logout?user_id=...&session_token=...`

Behavior:
- Password hashing uses PBKDF2-SHA256.
- Login returns expiring session token (7-day expiry).
- Register auto-logs the user in.

## 2. Game Flow

- Onboarding pool: 50 items
- Required onboarding picks: exactly 10
- Prefix rating required after onboarding
- Default rounds: 5
- Candidate set per round: 10
- Round scoring: AI vs human
- Final summary: learned preferences, hidden preferences, recommendations

Primary endpoints:
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

## 3. Data Utilities

### Dataset loading
From repo root:

```bash
docker compose exec backend python -m scripts.load_db
```

Optional movie ingestion:

```bash
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
```

`--max-movies` is optional if you want to cap final upserts.
For a fresh ingest strategy/target, add `--no-resume`.

### Local DB utility
From `backend/`:

```bash
python test.py summary
python test.py list-collections
python test.py clear-games
python test.py clear-products --category movies
```

## 4. Backup/Restore

Backup from Docker Postgres to local file:

```bash
docker compose exec -T postgres pg_dump -U decidio -d decidio -Fc > decidio.db
```

Restore directly into live DB:

```bash
docker compose exec -T postgres pg_restore -U decidio -d decidio --clean --if-exists < decidio.db
```

If restore reports constraint/index conflicts, use schema reset + restore flow documented in `docs/NGINX_SETUP.md`.

## 5. Frontend API URL

Frontend reads API base from `VITE_API_BASE_URL`.

Current compose default:

```yaml
VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8015}
```

- For local frontend: fallback works.
- For hosted frontend (Render): set `VITE_API_BASE_URL` to public HTTPS backend URL.
