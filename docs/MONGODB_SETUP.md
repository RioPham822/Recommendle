# MongoDB Setup (Deprecated)

This project no longer uses MongoDB.

## Current Database

- Active backend database: Postgres
- ORM/driver: SQLAlchemy + asyncpg
- Default local DB URL is configured in `backend/.env` as `DATABASE_URL`

## What to use instead

- Local/Docker setup: see `README.md`
- Public VM + Nginx setup: see `docs/NGINX_SETUP.md`
- Data loading scripts: `backend/scripts/load_db.py`, `backend/scripts/ingest_movies_tmdb.py`

## Why this file exists

This file is kept to avoid broken links from older docs/history. Use the Postgres docs above for all current setup.
