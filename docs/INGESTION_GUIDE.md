# Ingestion Guide

This guide documents the dataset ingestion scripts and their command-line arguments.

Current ingestion targets:
- TMDB movies via `backend/scripts/ingest_movies_tmdb.py`
- IGDB games via `backend/scripts/ingest_games_igdb.py`

Run commands from `backend/` when using plain Python, or from the repo root when using Docker.

## Movie Ingest

Script:

```bash
python -m scripts.ingest_movies_tmdb
```

Docker example:

```bash
docker compose exec backend python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
```

Required setup:
- set `TMDB_API_KEY` in `backend/.env`

### Arguments

- `--max-movies <int>`
  - optional cap on final upserts after filtering and diversity balancing
- `--start-year <int>`
  - earliest release year to scan
  - default: `1950`
- `--end-year <int>`
  - latest release year to scan from
  - default: current year
- `--no-resume`
  - ignore the checkpoint file and rebuild the candidate pool from scratch
- `--min-vote-count <int>`
  - hard quality filter for minimum TMDB `vote_count`
  - default: `1000`
  - this now matches the backend movie visibility threshold used by normal search/gameplay
- `--max-candidates <int>`
  - maximum candidate ids to evaluate before final selection
  - default: `2500`
- `--include-tmdb-raw`
  - stores the raw TMDB payload under `tmdb_raw`
- `--max-rps <float>`
  - request pacing limit with retry/backoff still applied
  - default: `8.0`
- `--max-pages-per-lane <int>`
  - maximum pages to fetch for each candidate-discovery lane
  - default: `20`
- `--lane-bars`
  - show grouped live progress bars when running in an interactive terminal

### Behavior Summary

The movie ingest pipeline:
1. builds a large candidate pool using multiple TMDB lane queries
2. fetches details for each candidate
3. applies hard quality filters
4. computes a soft quality score
5. optionally diversity-balances the final selected set
6. upserts results into Postgres as category `movies`

Checkpoint file:
- `backend/data/tmdb_ingest_checkpoint.json`

Useful examples:

```bash
python -m scripts.ingest_movies_tmdb --max-candidates 3000 --max-rps 8
python -m scripts.ingest_movies_tmdb --max-movies 1000 --max-candidates 8000
python -m scripts.ingest_movies_tmdb --max-candidates 3000 --no-resume
python -m scripts.ingest_movies_tmdb --include-tmdb-raw --lane-bars
```

## Game Ingest

Script:

```bash
python -m scripts.ingest_games_igdb
```

Docker example:

```bash
docker compose exec backend python -m scripts.ingest_games_igdb --max-candidates 5000
```

Required setup:
- set `IGDB_CLIENT_ID` and `IGDB_CLIENT_SECRET` in `backend/.env`

### Arguments

- `--max-games <int>`
  - optional cap on final upserts after filtering and diversity balancing
- `--start-year <int>`
  - earliest release year to scan
  - default: `1980`
- `--end-year <int>`
  - latest release year to scan from
  - default: current year
- `--no-resume`
  - ignore the checkpoint file and rebuild the candidate pool from scratch
- `--min-rating-count <int>`
  - hard quality filter for minimum `total_rating_count`
  - default: `20`
- `--min-total-rating <float>`
  - hard quality filter for minimum `total_rating` on the 0 to 100 scale
  - default: `60.0`
- `--max-candidates <int>`
  - maximum candidate ids to evaluate before final selection
  - default: `5000`
- `--max-pages-per-lane <int>`
  - maximum pages to fetch per lane while building the candidate pool
  - default: `20`
- `--include-igdb-raw`
  - stores the raw IGDB payload under `igdb_raw`
- `--max-rps <float>`
  - request pacing limit with retry/backoff still applied
  - default: `4.0`
- `--detail-batch-size <int>`
  - number of ids to include per details request batch
  - default: `100`
- `--lane-bars`
  - show grouped live progress bars when running in an interactive terminal

### Behavior Summary

The game ingest pipeline:
1. gets a Twitch access token for IGDB
2. builds a candidate pool from multiple IGDB APICalypse lanes
3. fetches details in batches
4. applies hard quality filters
5. computes a soft quality score
6. optionally diversity-balances the final selected set
7. upserts results into Postgres as category `games`

Checkpoint file:
- `backend/data/igdb_ingest_checkpoint.json`

Useful examples:

```bash
python -m scripts.ingest_games_igdb --max-candidates 5000
python -m scripts.ingest_games_igdb --max-games 1500 --max-candidates 9000
python -m scripts.ingest_games_igdb --max-candidates 5000 --no-resume
python -m scripts.ingest_games_igdb --detail-batch-size 200 --lane-bars
```

## Resume And Checkpoints

Both ingest scripts support resumable runs.

General behavior:
- by default they try to reuse an existing checkpoint
- `--no-resume` forces a fresh run
- if important configuration values change, the script may rebuild the candidate pool instead of resuming

Current checkpoint files:
- `backend/data/tmdb_ingest_checkpoint.json`
- `backend/data/igdb_ingest_checkpoint.json`

## Choosing Values

General guidance:
- increase `--max-candidates` when you want a broader search pool
- use `--max-movies` or `--max-games` when you want a capped final dataset
- increase `--max-pages-per-lane` when you want deeper candidate discovery
- reduce `--max-rps` if the upstream API becomes rate-limit sensitive
- use `--lane-bars` for interactive long-running local runs
- use `--no-resume` when changing strategy and you want a completely fresh candidate pool
