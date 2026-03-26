# Nginx Reverse Proxy Setup (Decidio Backend)

This guide explains how to expose the Docker backend (`127.0.0.1:8015`) as a public HTTPS API URL that your hosted frontend can call.

## Why This Is Needed

`http://localhost:8015` only works on the same machine.
A hosted frontend (for example Render) must call a public URL like `https://sd-vm23.csc.ncsu.edu`.

## Current Compose Security Model

The current `docker-compose.yml` already follows a safer setup:

- Postgres is bound to localhost: `127.0.0.1:5432:5432`
- Backend is bound to localhost: `127.0.0.1:8015:8015`
- Frontend is local-only and optional via profile:
  - `profiles: ["local-frontend"]`
  - `127.0.0.1:5173:5173`

This means public traffic should come through Nginx on ports `80/443`, not directly to backend/frontend container ports.

## Prerequisites

- VM allows inbound TCP ports `80` and `443`
- TLS certificate and key available under `/etc/pki/tls/`
- Nginx installed and running on VM

## 1. Start Services (Choose Mode)

### Backend only (Render frontend)

From repo root:

```bash
docker compose up -d postgres backend
```

### Local frontend + backend (for testing on VM)

```bash
docker compose --profile local-frontend up -d --build
```

## 2. Verify Backend Is Reachable Locally

```bash
curl http://127.0.0.1:8015/api/game/categories
```

## 3. Prepare Nginx Config

Project template files:

- `deploy/nginx/decidio.conf`
- `deploy/nginx/decidio.conf.example`

Your current config uses:

- `server_name sd-vm23.csc.ncsu.edu`
- `ssl_certificate /etc/pki/tls/certs/sd-vm23.csc.ncsu.edu.crt`
- `ssl_certificate_key /etc/pki/tls/private/sd-vm23.csc.ncsu.edu.key`
- `proxy_pass http://127.0.0.1:8015`

If your key is in a different folder, update the key path accordingly.

## 4. Install Config on VM

Copy the config to Nginx:

```bash
sudo cp deploy/nginx/decidio.conf /etc/nginx/conf.d/decidio.conf
```

Validate syntax:

```bash
sudo nginx -t
```

Reload Nginx:

```bash
sudo systemctl reload nginx
```

## 5. Verify backend is reachable in VM

```bash
curl https://sd-vm23.csc.ncsu.edu/api/game/categories
```

## 6. Frontend Environment Variable (`VITE_API_BASE_URL`)

### Render frontend

In Render service environment:

```env
VITE_API_BASE_URL=https://sd-vm23.csc.ncsu.edu
```

Redeploy frontend after changing this.

### Local Docker frontend

Current compose value:

```yaml
VITE_API_BASE_URL: ${VITE_API_BASE_URL:-http://localhost:8015}
```

Meaning:

- If host env var `VITE_API_BASE_URL` is set, Docker uses it.
- Otherwise Docker falls back to `http://localhost:8015`.

Examples:

```bash
# Uses fallback http://localhost:8015
docker compose --profile local-frontend up -d --build frontend

# Overrides fallback and uses public backend URL
VITE_API_BASE_URL=https://sd-vm23.csc.ncsu.edu docker compose --profile local-frontend up -d --build frontend
```

Note: Vite reads `VITE_*` values at build/start time. Rebuild/recreate frontend when the value changes.

## 7. CORS

Backend CORS is configured in `backend/app/main.py`.
Ensure your hosted frontend origin is included, e.g.:

- `https://recommendle-frontend.onrender.com`

After CORS changes:

```bash
docker compose up -d --build backend
```

## Troubleshooting

- `502 Bad Gateway`: backend not running on `127.0.0.1:8015`
- TLS errors: wrong cert/key path or permissions
- Browser mixed-content error: frontend is `https` but API URL is `http`
- CORS error: frontend origin missing in backend `allowed_origins`
- Public `:8015` exposure: check bind address is localhost only
  - `ss -tulpen | grep 8015`

## Postgres Backup and Restore (Docker)

This project uses Postgres in Docker (`postgres` service). You can back up to a local file and restore back into Docker when needed.

### 1. Dump Postgres to a local file

From repo root:

```bash
docker compose exec -T postgres pg_dump -U decidio -d decidio -Fc > decidio.db
```

Notes:

- `-Fc` creates a Postgres custom-format backup (not SQLite), even if the file extension is `.db`.
- Keep this file safe; it contains your application data.

### 2. Restore local dump directly into live Docker DB (`decidio`)

```bash
docker compose exec -T postgres pg_restore -U decidio -d decidio --clean --if-exists < decidio.db
```

This replaces existing objects in the live app database. After restore, restart backend so caches/models refresh cleanly:

```bash
docker compose up -d --build backend
```
