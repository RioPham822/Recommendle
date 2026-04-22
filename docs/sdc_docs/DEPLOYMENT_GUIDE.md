# Deployment Guide

This guide describes how to deploy Recommendle to a production-like server for sponsor delivery. It is written for developers or IT operations staff who can administer a Linux VM, Docker, Postgres, DNS, TLS certificates, and Nginx.

Recommendle is a web application with:
- a FastAPI backend
- a React frontend
- a Postgres database
- Docker Compose orchestration
- Nginx as the public HTTPS reverse proxy

The production deployment should not use test or dummy data. Load only the data approved for sponsor delivery.

## 1. Production Architecture

Recommended production layout:

- Public traffic enters through Nginx on ports `80` and `443`.
- Nginx terminates HTTPS and proxies API traffic to the backend on `127.0.0.1:8015`.
- Postgres runs in Docker and is bound only to `127.0.0.1:5432`.
- The backend runs in Docker and is bound only to `127.0.0.1:8015`.
- The frontend is deployed as a production static build on a static hosting service or production web server.

Do not expose Postgres or the backend Docker ports directly to the public internet.

## 2. Prerequisites

Install these on the production server:

- Git
- Docker Engine
- Docker Compose plugin
- Nginx
- TLS certificate and private key for the backend API domain
- Node.js 20 or newer on the machine used to build the frontend static assets

Example Ubuntu installation commands:

```bash
sudo apt-get update
sudo apt-get install -y git nginx ca-certificates curl
curl -fsSL https://get.docker.com | sudo sh
sudo usermod -aG docker "$USER"
```

Log out and back in after adding your user to the `docker` group.

Verify installation:

```bash
docker --version
docker compose version
nginx -v
```

## 3. Get The Application Source

Clone the repository into a production application directory:

```bash
sudo mkdir -p /opt/recommendle
sudo chown "$USER":"$USER" /opt/recommendle
git clone https://github.com/ncstate-csc-sdc/2026Spring-Team42-Decidio-3.git /opt/recommendle/app
cd /opt/recommendle/app
```

For a sponsor handoff, deploy from the approved release tag or commit:

```bash
git checkout <release-tag-or-commit>
```

## 4. Configure Environment Variables

Create `backend/.env` from the example:

```bash
cp backend/.env.example backend/.env
chmod 600 backend/.env
```

Edit `backend/.env`:

```bash
nano backend/.env
```

Required production values:

```env
DATABASE_URL=postgresql+asyncpg://decidio:<strong-password>@postgres:5432/decidio
DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
ADMIN_USERNAME=<admin-username>
ADMIN_PASSWORD=<strong-admin-password>
ADMIN_DISPLAY_NAME=Administrator
TMDB_API_KEY=
IGDB_CLIENT_ID=
IGDB_CLIENT_SECRET=
```

Notes:
- Use a strong Postgres password and match it in `docker-compose.yml`.
- Replace the default admin password before first startup.
- Leave TMDB and IGDB credentials empty unless production movie/game ingestion is required.
- Keep `backend/.env` out of source control.

Update the Postgres password in `docker-compose.yml` so it matches `DATABASE_URL`:

```yaml
POSTGRES_PASSWORD: <strong-password>
DATABASE_URL: postgresql+asyncpg://decidio:<strong-password>@postgres:5432/decidio
```

## 5. Build And Start Backend Services

From the repository root:

```bash
cd /opt/recommendle/app
docker compose pull postgres
docker compose build backend
docker compose up -d postgres backend
```

Check service status:

```bash
docker compose ps
docker compose logs --tail=100 backend
```

The backend creates required database tables on startup.

## 6. Load Production Data

Load only sponsor-approved production data. Do not load test or dummy records.

The bundled fountain pen dataset can be loaded when it is part of the approved production dataset:

```bash
docker compose exec backend python -m scripts.load_db
```

If movies or games are required, configure the matching API credentials in `backend/.env` and run the ingestion commands approved for the deployment:

```bash
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
```

After loading data, verify category inventory:

```bash
curl http://127.0.0.1:8015/api/game/categories
```

Each playable category should have enough visible items for the frontend readiness rule. The current frontend expects at least 100 visible items.

## 7. Configure Nginx For HTTPS

Copy the project Nginx template:

```bash
sudo cp deploy/nginx/decidio.conf.example /etc/nginx/conf.d/recommendle-api.conf
```

Edit the config:

```bash
sudo nano /etc/nginx/conf.d/recommendle-api.conf
```

Set:

```nginx
server_name api.example.com;
ssl_certificate     /etc/pki/tls/certs/api.example.com.crt;
ssl_certificate_key /etc/pki/tls/private/api.example.com.key;
proxy_pass http://127.0.0.1:8015;
```

Validate and reload Nginx:

```bash
sudo nginx -t
sudo systemctl reload nginx
```

Security recommendations:
- Serve the API only through HTTPS.
- Redirect HTTP to HTTPS.
- Keep backend and Postgres bound to localhost.
- Restrict SSH access to trusted operators.
- Store TLS keys with restrictive permissions.
- Keep Docker, OS packages, and Nginx patched.

## 8. Deploy The Frontend

The frontend should be deployed as a production static build, not with the Vite development server.

On the frontend build machine:

```bash
cd /opt/recommendle/app/frontend
npm ci
VITE_API_BASE_URL=https://api.example.com npm run build
```

Deploy the generated `frontend/dist/` directory to a production static host, such as Render Static Sites, Netlify, S3/CloudFront, or an Nginx static site.

If hosting the frontend on the same Nginx server, copy `frontend/dist/` to a web root such as:

```bash
sudo mkdir -p /var/www/recommendle
sudo cp -r dist/* /var/www/recommendle/
```

Then configure an HTTPS Nginx server block for the frontend domain that serves `/var/www/recommendle`.

Update backend CORS in `backend/app/main.py` if the production frontend origin is different from the existing allowed origins. Rebuild the backend after changing CORS:

```bash
docker compose up -d --build backend
```

## 9. Create The First Users

The backend can create a bootstrap admin account at startup from:

```env
ADMIN_USERNAME=<admin-username>
ADMIN_PASSWORD=<strong-admin-password>
ADMIN_DISPLAY_NAME=Administrator
```

After deployment:

1. Open the production frontend URL.
2. Log in with the bootstrap admin account.
3. Confirm the admin screen is accessible.
4. Create normal user accounts through the registration flow as needed.

If no bootstrap admin is configured, the first registered account becomes an admin.

## 10. Verification Plan

Run these checks after installation.

Check Docker services:

```bash
docker compose ps
```

Expected result:
- `postgres` is healthy/running.
- `backend` is running.

Check backend logs:

```bash
docker compose logs --tail=100 backend
```

Expected result:
- startup completes without database connection errors.

Check local API:

```bash
curl http://127.0.0.1:8015/api/game/categories
```

Expected result:
- JSON array of supported categories and inventory counts.

Check public HTTPS API:

```bash
curl https://api.example.com/api/game/categories
```

Expected result:
- same category JSON through HTTPS.

Check user registration or login:

```bash
curl -X POST https://api.example.com/api/auth/login \
  -H "Content-Type: application/json" \
  -d "{\"username\":\"<admin-username>\",\"password\":\"<strong-admin-password>\"}"
```

Expected result:
- response includes a session token and user details.

Check frontend:
- Open the production frontend URL in a browser.
- Log in.
- Confirm categories load.
- Start a game in a category with at least 100 visible items.
- Complete onboarding or choose a ready persona profile if one has been prepared.
- Start a round and confirm candidates appear.

## 11. Backup And Restore

Create a Postgres backup:

```bash
cd /opt/recommendle/app
docker compose exec -T postgres pg_dump -U decidio -d decidio -Fc > recommendle-production.dump
chmod 600 recommendle-production.dump
```

Restore a backup:

```bash
docker compose exec -T postgres pg_restore -U decidio -d decidio --clean --if-exists < recommendle-production.dump
docker compose up -d --build backend
```

Store backups securely because they contain user and gameplay data.

## 12. Troubleshooting

Backend cannot connect to Postgres:
- Run `docker compose ps` and confirm Postgres is healthy.
- Confirm `DATABASE_URL` uses host `postgres` inside Docker, not `localhost`.
- Confirm the password in `backend/.env` matches `docker-compose.yml`.
- Check `docker compose logs postgres`.

Public API returns `502 Bad Gateway`:
- Confirm backend is running: `docker compose ps`.
- Confirm the backend responds locally: `curl http://127.0.0.1:8015/api/game/categories`.
- Confirm Nginx `proxy_pass` points to `http://127.0.0.1:8015`.
- Run `sudo nginx -t` and reload Nginx.

Browser shows CORS errors:
- Confirm the frontend uses the HTTPS API URL in `VITE_API_BASE_URL`.
- Add the production frontend origin to backend CORS configuration.
- Rebuild/restart the backend.

Browser shows mixed-content errors:
- Confirm the frontend calls `https://api.example.com`, not `http://...`.
- Rebuild the frontend after changing `VITE_API_BASE_URL`.

Login fails for the bootstrap admin:
- Confirm `ADMIN_USERNAME` and `ADMIN_PASSWORD` were set before first startup.
- Check backend logs for bootstrap admin creation.
- If the user already exists, the backend promotes it to admin but does not reset its password.

Categories appear empty or unavailable:
- Confirm production data has been loaded.
- Run `curl http://127.0.0.1:8015/api/game/categories`.
- Confirm the category has at least 100 visible items for frontend readiness.

TLS certificate errors:
- Confirm certificate and key paths in Nginx.
- Confirm file permissions allow Nginx to read the key.
- Confirm DNS points the API domain to the production server.

Frontend shows stale API URL:
- Rebuild the frontend after setting `VITE_API_BASE_URL`.
- Redeploy the generated `dist/` files.
