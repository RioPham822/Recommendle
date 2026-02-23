"""
Ingest movies from TMDB into Postgres products table (category=movies).

Usage:
    cd backend
    python -m scripts.ingest_movies_tmdb --max-movies 1000
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import and_, select
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
CHECKPOINT_PATH = DATA_DIR / "tmdb_ingest_checkpoint.json"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


def _load_checkpoint() -> dict[str, Any]:
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(data: dict[str, Any]) -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _runtime_bucket(minutes: int | None) -> str | None:
    if minutes is None:
        return None
    if minutes < 90:
        return "short"
    if minutes <= 130:
        return "medium"
    return "long"


def _decade_bucket(year: int | None) -> str | None:
    if year is None:
        return None
    return f"{(year // 10) * 10}s"


def _build_movie_doc(movie: dict[str, Any]) -> dict[str, Any]:
    release_date = str(movie.get("release_date") or "")
    release_year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
    runtime = movie.get("runtime")
    runtime_minutes = int(runtime) if isinstance(runtime, (int, float)) else None

    genres = [g.get("name") for g in (movie.get("genres") or []) if g.get("name")]
    keywords = [k.get("name") for k in ((movie.get("keywords") or {}).get("keywords") or []) if k.get("name")]
    companies = [c.get("name") for c in (movie.get("production_companies") or []) if c.get("name")]
    directors = [
        c.get("name")
        for c in (movie.get("credits") or {}).get("crew") or []
        if c.get("job") == "Director" and c.get("name")
    ]

    primary_country = None
    countries = movie.get("production_countries") or []
    if countries:
        primary_country = countries[0].get("iso_3166_1")

    certification = None
    for country_row in ((movie.get("release_dates") or {}).get("results") or []):
        if country_row.get("iso_3166_1") == "US":
            for rel in country_row.get("release_dates") or []:
                cert = rel.get("certification")
                if cert:
                    certification = cert
                    break
            if certification:
                break

    poster_path = movie.get("poster_path")
    images: list[dict[str, Any]] = []
    if poster_path:
        images.append({"url": f"{TMDB_IMAGE_BASE}{poster_path}", "alt": movie.get("title"), "position": 0})

    source_id = str(movie.get("id"))
    title = str(movie.get("title") or "Untitled")
    vote_average = float(movie["vote_average"]) if movie.get("vote_average") is not None else None
    popularity = float(movie["popularity"]) if movie.get("popularity") is not None else None

    return {
        "schema_version": 2,
        "source_id": source_id,
        "title": title,
        "vendor": companies[0] if companies else None,
        "product_type": "movie",
        "price_min": None,
        "price_max": None,
        "currency": "USD",
        "tags": genres[:8],
        "options": {},
        "release_year": release_year,
        "runtime_minutes": runtime_minutes,
        "vote_average": vote_average,
        "popularity": popularity,
        "original_language": movie.get("original_language"),
        "certification": certification,
        "primary_country": primary_country,
        "decade_bucket": _decade_bucket(release_year),
        "runtime_bucket": _runtime_bucket(runtime_minutes),
        "genres": genres,
        "keywords": keywords,
        "production_companies": companies,
        "directors": directors,
        "description": movie.get("overview"),
        "url": f"https://www.themoviedb.org/movie/{source_id}",
        "images": images,
    }


def _tmdb_get(api_key: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    query = {"api_key": api_key}
    if params:
        query.update(params)
    resp = requests.get(f"{TMDB_BASE_URL}{path}", params=query, timeout=30)
    resp.raise_for_status()
    return resp.json()


async def ingest_movies(
    *,
    max_movies: int,
    start_year: int,
    end_year: int,
    resume: bool,
) -> None:
    from app.db import ProductRecord, get_db, init_db, settings

    api_key = (settings.tmdb_api_key or "").strip()
    if not api_key:
        raise SystemExit("TMDB_API_KEY is missing in backend/.env")

    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)

    checkpoint = _load_checkpoint() if resume else {}
    year = int(checkpoint.get("current_year", end_year))
    page = int(checkpoint.get("next_page", 1))
    upserted = int(checkpoint.get("upserted_count", 0))

    pbar = tqdm(total=max_movies, initial=min(upserted, max_movies), desc="Ingesting movies")

    try:
        while year >= start_year and upserted < max_movies:
            discover = _tmdb_get(
                api_key,
                "/discover/movie",
                {
                    "sort_by": "popularity.desc",
                    "include_adult": "false",
                    "include_video": "false",
                    "primary_release_year": year,
                    "page": page,
                },
            )
            results = discover.get("results") or []
            total_pages = int(discover.get("total_pages") or 1)

            if not results:
                year -= 1
                page = 1
                continue

            for row in results:
                if upserted >= max_movies:
                    break
                movie_id = row.get("id")
                if not movie_id:
                    continue

                detail = _tmdb_get(
                    api_key,
                    f"/movie/{movie_id}",
                    {"append_to_response": "credits,keywords,release_dates"},
                )
                doc = _build_movie_doc(detail)
                source_id = doc["source_id"]
                existing = await db.scalar(
                    select(ProductRecord).where(
                        and_(
                            ProductRecord.category == "movies",
                            ProductRecord.data["source_id"].as_string() == source_id,
                        )
                    )
                )
                if existing:
                    existing.data = doc
                else:
                    db.add(
                        ProductRecord(
                            category="movies",
                            data=doc,
                            created_at=datetime.now(timezone.utc),
                        )
                    )

                upserted += 1
                pbar.update(1)

                if upserted % 100 == 0:
                    await db.commit()
                    _save_checkpoint(
                        {
                            "current_year": year,
                            "next_page": page,
                            "upserted_count": upserted,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )

            page += 1
            if page > total_pages:
                year -= 1
                page = 1

        await db.commit()
        _save_checkpoint(
            {
                "current_year": year,
                "next_page": page,
                "upserted_count": upserted,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        pbar.close()
        await db_gen.aclose()

    print(f"[tmdb] completed upserts: {upserted}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest TMDB movies into Postgres")
    parser.add_argument("--max-movies", type=int, default=1000, help="Maximum number of movies to ingest")
    parser.add_argument("--start-year", type=int, default=1950, help="Earliest release year to scan")
    parser.add_argument("--end-year", type=int, default=datetime.now().year, help="Latest release year to start from")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint and start fresh")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(
        ingest_movies(
            max_movies=max(1, int(args.max_movies)),
            start_year=int(args.start_year),
            end_year=int(args.end_year),
            resume=not args.no_resume,
        )
    )


if __name__ == "__main__":
    main()
