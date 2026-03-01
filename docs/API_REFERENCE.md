# API Reference

Current backend API reference for this repository.

Base URL examples:
- Local: `http://localhost:8015`
- Public (via Nginx): `https://sd-vm23.csc.ncsu.edu`

## Authentication

### POST `/api/auth/register`
Register a new user and auto-login.

Request body:
```json
{
  "username": "alice",
  "password": "MyPassword123",
  "display_name": "Alice Smith"
}
```

### POST `/api/auth/login`
Login and return session token.

Request body:
```json
{
  "username": "alice",
  "password": "MyPassword123"
}
```

### GET `/api/auth/user/{user_id}`
Get public user profile.

### POST `/api/auth/change-password?user_id={user_id}`
Change password.

Request body:
```json
{
  "old_password": "MyPassword123",
  "new_password": "NewPassword456"
}
```

Note: current backend expects `user_id` as query parameter.

### POST `/api/auth/logout?user_id={user_id}&session_token={token}`
Invalidate one session token.

Note: current backend expects both values as query parameters.

## Game APIs

- `GET /api/game/categories`
- `POST /api/game/start`
- `GET /api/game/resume-state?player_name=...&category=...`
- `GET /api/game/{game_id}/onboarding`
- `POST /api/game/{game_id}/onboarding/submit`
- `POST /api/game/{game_id}/round/start`
- `POST /api/game/{game_id}/round/{round_number}/pick`
- `GET /api/game/{game_id}/status`
- `GET /api/game/{game_id}/summary`
- `GET /api/game/leaderboard?limit=10&category=fountain_pens`
- `GET /api/game/player/{player_name}/history?category=fountain_pens&limit=20`

## Product APIs

- `GET /api/products`
- `GET /api/products/{product_id}`

## Backend DB Utility (`backend/test.py`)

From `backend/`:

```bash
python test.py summary
python test.py list-collections
python test.py clear-games
```

Available commands are currently limited to the three above.

## Example cURL

```bash
curl -X POST http://localhost:8015/api/auth/register \
  -H "Content-Type: application/json" \
  -d '{"username":"alice","password":"MyPassword123","display_name":"Alice"}'
```

```bash
curl -X POST "http://localhost:8015/api/auth/logout?user_id=<USER_ID>&session_token=<TOKEN>"
```
