# API Reference

Current backend API reference for the Postgres-backed application.

Base URLs:
- Local: `http://localhost:8015`
- Public backend example: `https://api.example.com`

Authentication headers used by protected routes:
- `Authorization: Bearer <session_token>`
- `X-User-Id: <user_id>`

## Auth API

### POST `/api/auth/register`

Creates a user and returns an auth token.

Request body:

```json
{
  "username": "alice",
  "password": "MyPassword123",
  "display_name": "Alice Smith"
}
```

### POST `/api/auth/login`

Logs in and returns an auth token.

Request body:

```json
{
  "username": "alice",
  "password": "MyPassword123"
}
```

### GET `/api/auth/user/{user_id}`

Returns the public user profile.

### POST `/api/auth/change-password?user_id={user_id}`

Changes the password for a user id.

Request body:

```json
{
  "old_password": "MyPassword123",
  "new_password": "NewPassword456"
}
```

Note:
- the backend currently expects `user_id` as a query parameter

### POST `/api/auth/logout?user_id={user_id}&session_token={token}`

Invalidates one session token.

## Game API

### Core session endpoints

- `GET /api/game/categories`
- `GET /api/game/personas?category=movies`
- `POST /api/game/start`
- `GET /api/game/resume-state?player_name=...&category=...`
- `GET /api/game/{game_id}/status`
- `GET /api/game/{game_id}/summary`
- `GET /api/game/leaderboard?limit=10&category=fountain_pens`
- `GET /api/game/player/{player_name}/history?category=fountain_pens&limit=20`

### Onboarding endpoints

- `GET /api/game/{game_id}/onboarding`
- `POST /api/game/{game_id}/onboarding/submit`
- `POST /api/game/{game_id}/onboarding/refresh`

### Round endpoints

- `POST /api/game/{game_id}/round/start`
- `POST /api/game/{game_id}/round/{round_number}/pick`
- `POST /api/game/{game_id}/round/refresh`

### Beta-mode and redesign endpoints

- `POST /api/game/{game_id}/seed`
- `POST /api/game/{game_id}/feedback`
- `PATCH /api/game/{game_id}/preferences`

Notes:
- `POST /api/game/start` and `GET /api/game/resume-state` will bind to the authenticated user display name when auth headers are present.
- `GET /api/game/personas` returns only completed, playable persona profiles. Use `category` to filter the list.
- `POST /api/game/start` accepts an optional `persona_id`. When present, the backend copies that persona's latest completed profile into the fresh game and returns a ready game that skips onboarding.
- `seed` and `feedback` are only valid for `beta` mode sessions.
- `preferences` editing is only valid after onboarding has completed for redesigned sessions.

## Product API

- `GET /api/products`
- `GET /api/products/search?q=...&category=movies&limit=12&fuzzy=true`
- `GET /api/products/{product_id}`

Notes:
- movie search and product visibility are filtered by the backend so movie records with TMDB `vote_count < 1000` are hidden from normal gameplay/search

## Admin API

All admin routes require valid auth headers for an admin user.

- `GET /api/admin/me`
- `GET /api/admin/users`
- `DELETE /api/admin/users/{user_id}`
- `POST /api/admin/users/{user_id}/progress/clear`
- `GET /api/admin/users/{user_id}/ml-stats`
- `GET /api/admin/ml-config`
- `PATCH /api/admin/ml-config`
- `GET /api/admin/categories`
- `GET /api/admin/products?category=...`
- `GET /api/admin/products/export?category=...`
- `GET /api/admin/personas`
- `POST /api/admin/persona-runs`
- `GET /api/admin/persona-runs?limit=40`
- `GET /api/admin/persona-runs/{run_id}`

Admin product query params:
- `category` is required
- `search` is optional
- `filters` is optional JSON
- `limit`, `offset`, `sort_field`, `sort_dir` are supported

Admin persona simulation notes:
- `GET /api/admin/personas` returns the bundled persona definitions.
- `POST /api/admin/persona-runs` starts a background simulation and supersedes older active runs for the same persona.
- A successful run refreshes the persona's canonical playable profile for public starts.
- Run details include status, timeline events, metrics, game status, and final summary when available.

Persona run launch body:

```json
{
  "persona_id": "action-thriller-mainstream",
  "match_streak_target": 5,
  "max_rounds": 40
}
```

## Local Utility Script

From `backend/`:

```bash
python test.py summary
python test.py list-collections
python test.py clear-games
python test.py clear-products --category movies
python test.py export-movies-json --output data/movies_export.json
python test.py export-movies-excel --output data/movies_export.csv
```

## Example Requests

Register:

```bash
curl -X POST http://localhost:8015/api/auth/register \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"alice\",\"password\":\"MyPassword123\",\"display_name\":\"Alice\"}"
```

Start a game:

```bash
curl -X POST http://localhost:8015/api/game/start \
  -H "Content-Type: application/json" \
  -d "{\"player_name\":\"Alice\",\"category\":\"fountain_pens\",\"mode\":\"beta\"}"
```

Start from a ready persona:

```bash
curl -X POST http://localhost:8015/api/game/start \
  -H "Content-Type: application/json" \
  -d "{\"player_name\":\"Alice\",\"category\":\"movies\",\"mode\":\"beta\",\"fresh_start\":true,\"persona_id\":\"action-thriller-mainstream\"}"
```

Fetch categories:

```bash
curl http://localhost:8015/api/game/categories
```
