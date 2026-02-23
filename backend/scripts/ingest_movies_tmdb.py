"""
Ingest a large movie catalog from TMDB into MongoDB products collection.

Usage:
    cd backend
    set TMDB_API_KEY=...
    python -m scripts.ingest_movies_tmdb --max-movies 50000
"""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from pymongo import MongoClient

# Ensure `app.*` imports work whether run from repo root or backend/.
ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.db import settings


TMDB_BASE = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"


@dataclass
class IngestConfig:
    api_key: str
    max_movies: int
    language: str
    min_vote_count: int
    sleep_ms: int
    checkpoint_path: Path
    start_year: int
    end_year: int


def _request(
    api_key: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    retries: int = 4,
) -> dict[str, Any]:
    query = {"api_key": api_key}
    if params:
        query.update(params)
    url = f"{TMDB_BASE}{path}"

    last_error: Exception | None = None
    for attempt in range(retries):
        try:
            response = requests.get(url, params=query, timeout=30)
            response.raise_for_status()
            return response.json()
        except Exception as exc:  # noqa: BLE001
            last_error = exc
            backoff = 2 ** attempt
            time.sleep(backoff)
    if last_error:
        raise last_error
    raise RuntimeError("TMDB request failed unexpectedly")


def _slug(text: str) -> str:
    base = "".join(ch.lower() if ch.isalnum() else "-" for ch in text)
    while "--" in base:
        base = base.replace("--", "-")
    return base.strip("-")


def _decade_bucket(release_year: int | None) -> str | None:
    if not release_year:
        return None
    decade = (release_year // 10) * 10
    return f"{decade}s"


def _runtime_bucket(runtime_minutes: int | None) -> str | None:
    if runtime_minutes is None:
        return None
    if runtime_minutes < 90:
        return "short"
    if runtime_minutes <= 130:
        return "standard"
    return "long"


def _certification(detail: dict[str, Any], preferred_country: str = "US") -> str | None:
    releases = detail.get("release_dates", {}).get("results", [])
    first_non_empty: str | None = None
    for country_row in releases:
        iso = country_row.get("iso_3166_1")
        for rel in country_row.get("release_dates", []):
            cert = (rel.get("certification") or "").strip()
            if not cert:
                continue
            if iso == preferred_country:
                return cert
            if first_non_empty is None:
                first_non_empty = cert
    return first_non_empty


def _normalized_movie_doc(detail: dict[str, Any], *, language: str) -> dict[str, Any] | None:
    tmdb_id = detail.get("id")
    title = (detail.get("title") or "").strip()
    if not tmdb_id or not title:
        return None
    if detail.get("adult", False):
        return None

    release_date = (detail.get("release_date") or "").strip()
    release_year: int | None = None
    if len(release_date) >= 4 and release_date[:4].isdigit():
        release_year = int(release_date[:4])

    runtime = detail.get("runtime")
    if runtime is not None:
        try:
            runtime = int(runtime)
        except (TypeError, ValueError):
            runtime = None

    vote_average = detail.get("vote_average")
    popularity = detail.get("popularity")
    vote_count = int(detail.get("vote_count") or 0)

    companies = [
        (c.get("name") or "").strip()
        for c in detail.get("production_companies", [])
        if (c.get("name") or "").strip()
    ]
    directors = [
        (c.get("name") or "").strip()
        for c in detail.get("credits", {}).get("crew", [])
        if c.get("job") == "Director" and (c.get("name") or "").strip()
    ]
    genres = [
        (g.get("name") or "").strip()
        for g in detail.get("genres", [])
        if (g.get("name") or "").strip()
    ]
    keywords = [
        (k.get("name") or "").strip()
        for k in detail.get("keywords", {}).get("keywords", [])
        if (k.get("name") or "").strip()
    ]

    countries = [
        (c.get("iso_3166_1") or "").strip()
        for c in detail.get("production_countries", [])
        if (c.get("iso_3166_1") or "").strip()
    ]
    primary_country = countries[0] if countries else None

    poster_path = detail.get("poster_path")
    backdrop_path = detail.get("backdrop_path")
    images = []
    if poster_path:
        images.append({"url": f"{TMDB_IMAGE_BASE}{poster_path}", "alt": f"{title} poster", "position": 0})
    if backdrop_path:
        images.append({"url": f"{TMDB_IMAGE_BASE}{backdrop_path}", "alt": f"{title} backdrop", "position": 1})

    description = (detail.get("overview") or "").strip() or None
    certification = _certification(detail)
    language_code = (detail.get("original_language") or "").strip() or None

    return {
        "category": "movies",
        "schema_version": 2,
        "source_id": f"tmdb_movie_{tmdb_id}",
        "title": title,
        "handle": _slug(f"{title}-{tmdb_id}"),
        "vendor": companies[0] if companies else "Unknown Studio",
        "product_type": "Movie",
        "price_min": None,
        "price_max": None,
        "currency": "USD",
        "tags": genres[:6],
        "options": {},
        "release_year": release_year,
        "runtime_minutes": runtime,
        "vote_average": float(vote_average) if vote_average is not None else None,
        "popularity": float(popularity) if popularity is not None else None,
        "original_language": language_code,
        "certification": certification,
        "primary_country": primary_country,
        "decade_bucket": _decade_bucket(release_year),
        "runtime_bucket": _runtime_bucket(runtime),
        "genres": genres[:8],
        "keywords": keywords[:15],
        "production_companies": companies[:8],
        "directors": directors[:4],
        "description": description,
        "url": f"https://www.themoviedb.org/movie/{tmdb_id}",
        "images": images,
        "created_at": datetime.now(timezone.utc),
        "movie_vote_count": vote_count,
        "language_requested": language,
    }


def _passes_quality_filters(doc: dict[str, Any], *, min_vote_count: int) -> bool:
    if not doc.get("images"):
        return False
    if not doc.get("description"):
        return False
    if not doc.get("runtime_minutes"):
        return False
    if int(doc.get("movie_vote_count") or 0) < min_vote_count:
        return False
    return True


def _load_checkpoint(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {"next_page": 1, "upserted_count": 0}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001
        return {"next_page": 1, "upserted_count": 0}


def _save_checkpoint(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def ingest_movies(config: IngestConfig) -> None:
    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    products = db.products

    checkpoint = _load_checkpoint(config.checkpoint_path)
    upserted = int(checkpoint.get("upserted_count", 0))
    if "current_year" not in checkpoint:
        # Legacy checkpoint from single-stream paging mode: restart with year slicing.
        page = 1
        current_year = config.start_year
    else:
        page = max(int(checkpoint.get("next_page", 1)), 1)
        page = min(page, 500)
        current_year = int(checkpoint.get("current_year", config.start_year))
    current_year = min(max(current_year, config.end_year), config.start_year)

    print(
        f"Starting TMDB ingest at year {current_year}, page {page}, "
        f"existing upserts={upserted}"
    )
    while upserted < config.max_movies and current_year >= config.end_year:
        try:
            discover = _request(
                config.api_key,
                "/discover/movie",
                params={
                    "language": config.language,
                    "include_adult": "false",
                    "include_video": "false",
                    "sort_by": "popularity.desc",
                    "page": page,
                    "primary_release_year": current_year,
                },
            )
        except requests.HTTPError as exc:
            status = exc.response.status_code if exc.response is not None else None
            # Resilient handling for intermittent TMDB failures.
            if status in {408, 429, 500, 502, 503, 504}:
                print(
                    f"Transient TMDB error on year={current_year}, page={page}, "
                    f"status={status}; skipping page and continuing."
                )
                page += 1
                if page > 500:
                    current_year -= 1
                    page = 1
                _save_checkpoint(
                    config.checkpoint_path,
                    {
                        "current_year": current_year,
                        "next_page": page,
                        "upserted_count": upserted,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    },
                )
                continue
            raise
        results = discover.get("results", [])
        total_pages = int(discover.get("total_pages") or page)
        capped_total_pages = max(1, min(total_pages, 500))
        if not results:
            # No results for this year/page; advance to next year.
            current_year -= 1
            page = 1
            continue

        for summary in results:
            if upserted >= config.max_movies:
                break
            movie_id = summary.get("id")
            if not movie_id:
                continue
            try:
                detail = _request(
                    config.api_key,
                    f"/movie/{movie_id}",
                    params={
                        "language": config.language,
                        "append_to_response": "keywords,credits,release_dates",
                    },
                )
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                if status in {408, 429, 500, 502, 503, 504}:
                    print(f"Transient detail error for movie {movie_id} (status={status}); skipping.")
                    continue
                # Non-transient errors (e.g. 404) should not crash full ingest.
                print(f"Detail request failed for movie {movie_id} (status={status}); skipping.")
                continue

            doc = _normalized_movie_doc(detail, language=config.language)
            if not doc:
                continue
            if not _passes_quality_filters(doc, min_vote_count=config.min_vote_count):
                continue

            source_id = doc["source_id"]
            products.update_one(
                {"category": "movies", "source_id": source_id},
                {"$set": doc},
                upsert=True,
            )
            upserted += 1

            if upserted % 50 == 0:
                print(f"Upserted {upserted} movies...")

            time.sleep(max(config.sleep_ms, 0) / 1000.0)

        page += 1
        if page > capped_total_pages:
            print(
                f"Finished year {current_year} "
                f"(pages: {capped_total_pages}, upserts: {upserted})."
            )
            current_year -= 1
            page = 1

        _save_checkpoint(
            config.checkpoint_path,
            {
                "current_year": current_year,
                "next_page": page,
                "upserted_count": upserted,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            },
        )

    products.create_index([("category", 1), ("source_id", 1)], unique=True)
    products.create_index([("category", 1), ("title", 1)])
    products.create_index([("category", 1), ("release_year", 1)])
    products.create_index([("category", 1), ("vendor", 1)])
    print(f"Ingest complete. Total upserts this run reached: {upserted}")
    client.close()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Ingest movies from TMDB")
    parser.add_argument("--max-movies", type=int, default=50000)
    parser.add_argument("--language", type=str, default="en-US")
    parser.add_argument("--min-vote-count", type=int, default=100)
    parser.add_argument("--sleep-ms", type=int, default=50)
    parser.add_argument("--start-year", type=int, default=datetime.now(timezone.utc).year)
    parser.add_argument("--end-year", type=int, default=1950)
    parser.add_argument(
        "--checkpoint",
        type=str,
        default=str(ROOT_DIR / "data" / "tmdb_ingest_checkpoint.json"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    api_key = (settings.tmdb_api_key or "").strip()
    if not api_key:
        raise SystemExit("TMDB_API_KEY is required in backend/.env.")

    config = IngestConfig(
        api_key=api_key,
        max_movies=args.max_movies,
        language=args.language,
        min_vote_count=args.min_vote_count,
        sleep_ms=args.sleep_ms,
        checkpoint_path=Path(args.checkpoint),
        start_year=args.start_year,
        end_year=args.end_year,
    )
    ingest_movies(config)


if __name__ == "__main__":
    main()
