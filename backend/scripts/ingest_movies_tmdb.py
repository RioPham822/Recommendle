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
import math
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import requests
from sqlalchemy import and_, select
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from app.visibility import MOVIE_MIN_VISIBLE_VOTE_COUNT

DATA_DIR = ROOT_DIR / "data"
CHECKPOINT_PATH = DATA_DIR / "tmdb_ingest_checkpoint.json"
TMDB_BASE_URL = "https://api.themoviedb.org/3"
TMDB_IMAGE_BASE = "https://image.tmdb.org/t/p/w500"
STRATEGY_VERSION = 3
_REQUEST_MIN_INTERVAL_SECONDS = 0.0
_LAST_REQUEST_TS = 0.0


def _load_checkpoint() -> dict[str, Any]:
    """Load ingest checkpoint from disk, returning empty state on failure."""
    if not CHECKPOINT_PATH.exists():
        return {}
    try:
        return json.loads(CHECKPOINT_PATH.read_text(encoding="utf-8"))
    except Exception:
        return {}


def _save_checkpoint(data: dict[str, Any]) -> None:
    """Persist ingest checkpoint to disk."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHECKPOINT_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")


def _runtime_bucket(minutes: int | None) -> str | None:
    """Bucket runtime minutes into short/medium/long labels."""
    if minutes is None:
        return None
    if minutes < 90:
        return "short"
    if minutes <= 130:
        return "medium"
    return "long"


def _decade_bucket(year: int | None) -> str | None:
    """Convert year to decade label (for example, 1990s)."""
    if year is None:
        return None
    return f"{(year // 10) * 10}s"


def _build_movie_doc(movie: dict[str, Any]) -> dict[str, Any]:
    """Transform TMDB movie payload into canonical Postgres product document."""
    release_date = str(movie.get("release_date") or "")
    release_year = int(release_date[:4]) if len(release_date) >= 4 and release_date[:4].isdigit() else None
    runtime = movie.get("runtime")
    runtime_minutes = int(runtime) if isinstance(runtime, (int, float)) else None
    if runtime_minutes is not None and runtime_minutes <= 0:
        runtime_minutes = None

    genres = [g.get("name") for g in (movie.get("genres") or []) if g.get("name")]
    keywords = [k.get("name") for k in ((movie.get("keywords") or {}).get("keywords") or []) if k.get("name")]
    companies = [c.get("name") for c in (movie.get("production_companies") or []) if c.get("name")]
    directors = [
        c.get("name") for c in (movie.get("credits") or {}).get("crew") or [] if c.get("job") == "Director" and c.get("name")
    ]

    primary_country = None
    countries = movie.get("production_countries") or []
    if countries:
        primary_country = countries[0].get("iso_3166_1")

    certification = None
    for country_row in (movie.get("release_dates") or {}).get("results") or []:
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
    vote_count = int(movie.get("vote_count") or 0)
    has_poster = bool(poster_path)
    status = str(movie.get("status") or "").strip() or None
    is_classic = bool(
        release_year is not None
        and release_year <= 2000
        and vote_count >= 5000
        and (vote_average or 0.0) >= 7.5
    )

    return {
        "schema_version": 2,
        "source_id": source_id,
        "title": title,
        "vendor": companies[0] if companies else None,
        "release_year": release_year,
        "release_date": release_date or None,
        "runtime_minutes": runtime_minutes,
        "vote_average": vote_average,
        "vote_count": vote_count,
        "popularity": popularity,
        "status": status,
        "has_poster": has_poster,
        "is_classic": is_classic,
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


def _today_utc_date() -> str:
    """Return UTC date in YYYY-MM-DD format."""
    return datetime.now(timezone.utc).date().isoformat()


def _passes_quality_filters(doc: dict[str, Any], min_vote_count: int) -> bool:
    """Apply hard quality filters for gameplay-ready movie records."""
    release_date = doc.get("release_date")
    if not release_date or release_date > _today_utc_date():
        return False
    runtime = doc.get("runtime_minutes")
    if runtime is None or int(runtime) < 60:
        return False
    if not doc.get("has_poster"):
        return False
    genres = doc.get("genres") or []
    if len(genres) == 0:
        return False
    if int(doc.get("vote_count") or 0) < int(min_vote_count):
        return False
    return True


def _recency_bonus(release_year: int | None) -> float:
    """Map release year into a small 0..1 recency bonus."""
    if release_year is None:
        return 0.0
    now_year = datetime.now(timezone.utc).year
    if release_year > now_year:
        return 0.0
    age = max(0, now_year - release_year)
    return max(0.0, min(1.0, 1.0 - age / 30.0))


def _quality_score(doc: dict[str, Any]) -> float:
    """Compute weighted soft quality score for ranking candidates."""
    vote_count = max(0, int(doc.get("vote_count") or 0))
    vote_avg = max(0.0, min(10.0, float(doc.get("vote_average") or 0.0)))
    popularity = max(0.0, float(doc.get("popularity") or 0.0))
    recency = _recency_bonus(doc.get("release_year"))
    return (
        0.45 * math.log1p(vote_count)
        + 0.30 * vote_avg
        + 0.15 * math.log1p(popularity)
        + 0.10 * recency
    )


def _primary_genre(doc: dict[str, Any]) -> str:
    """Return one canonical genre for diversity balancing."""
    genres = doc.get("genres") or []
    if not genres:
        return "unknown"
    return str(genres[0]).strip().lower() or "unknown"


def _select_diverse_movies(candidates: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Select top movies with soft quota balancing by decade/genre/language."""
    if target <= 0 or not candidates:
        return []
    pool = list(candidates)
    selected: list[dict[str, Any]] = []
    count_decade: dict[str, int] = {}
    count_genre: dict[str, int] = {}
    count_lang: dict[str, int] = {}
    decade_target = max(1, int(target * 0.20))
    genre_target = max(1, int(target * 0.14))
    lang_target = max(1, int(target * 0.25))

    classic_target = max(1, int(target * 0.20))
    classic_candidates = [
        doc
        for doc in pool
        if bool(doc.get("is_classic"))
        or (
            (doc.get("release_year") or 9999) <= 2000
            and int(doc.get("vote_count") or 0) >= 5000
            and float(doc.get("vote_average") or 0.0) >= 7.5
        )
    ]
    classic_candidates.sort(key=lambda d: float(d.get("quality_score") or 0.0), reverse=True)
    for doc in classic_candidates[:classic_target]:
        selected.append(doc)
        if doc in pool:
            pool.remove(doc)
        decade = str(doc.get("decade_bucket") or "unknown")
        genre = _primary_genre(doc)
        lang = str(doc.get("original_language") or "unknown").lower()
        count_decade[decade] = count_decade.get(decade, 0) + 1
        count_genre[genre] = count_genre.get(genre, 0) + 1
        count_lang[lang] = count_lang.get(lang, 0) + 1

    while pool and len(selected) < target:
        best_idx = 0
        best_score = float("-inf")
        for idx, doc in enumerate(pool):
            decade = str(doc.get("decade_bucket") or "unknown")
            genre = _primary_genre(doc)
            lang = str(doc.get("original_language") or "unknown").lower()
            penalty = (
                0.35 * (count_decade.get(decade, 0) / decade_target)
                + 0.45 * (count_genre.get(genre, 0) / genre_target)
                + 0.20 * (count_lang.get(lang, 0) / lang_target)
            )
            adjusted = float(doc.get("quality_score") or 0.0) - penalty
            if adjusted > best_score:
                best_score = adjusted
                best_idx = idx
        chosen = pool.pop(best_idx)
        selected.append(chosen)
        chosen_decade = str(chosen.get("decade_bucket") or "unknown")
        chosen_genre = _primary_genre(chosen)
        chosen_lang = str(chosen.get("original_language") or "unknown").lower()
        count_decade[chosen_decade] = count_decade.get(chosen_decade, 0) + 1
        count_genre[chosen_genre] = count_genre.get(chosen_genre, 0) + 1
        count_lang[chosen_lang] = count_lang.get(chosen_lang, 0) + 1
    return selected


def _add_candidate(
    candidate_sources: dict[int, set[str]],
    ids: list[int],
    lane: str,
    cap: int,
) -> None:
    """Append IDs into candidate map while preserving insertion order."""
    for mid in ids:
        if len(candidate_sources) >= cap and mid not in candidate_sources:
            break
        candidate_sources.setdefault(mid, set()).add(lane)


def _lane_unique_counts(candidate_sources: dict[int, set[str]]) -> dict[str, int]:
    """Count unique candidate IDs attributed to each lane."""
    counts: dict[str, int] = {}
    for lanes in candidate_sources.values():
        for lane in lanes:
            counts[lane] = counts.get(lane, 0) + 1
    return counts


def _format_lane_counts(counts: dict[str, int]) -> str:
    """Format lane counts for log output."""
    if not counts:
        return "none"
    ordered = sorted(counts.items(), key=lambda item: (-item[1], item[0]))
    return ", ".join(f"{lane}={count}" for lane, count in ordered)


def _discover_ids(
    api_key: str,
    *,
    base_params: dict[str, Any],
    pages: int,
    cap: int,
) -> list[int]:
    """Collect movie IDs from discover endpoint for one lane."""
    ids: list[int] = []
    for page in range(1, max(1, pages) + 1):
        params = dict(base_params)
        params["page"] = page
        payload = _tmdb_get(api_key, "/discover/movie", params)
        results = payload.get("results") or []
        if not results:
            break
        for row in results:
            mid = row.get("id")
            if isinstance(mid, int):
                ids.append(mid)
                if len(ids) >= cap:
                    return ids
    return ids


def _trending_ids(api_key: str, *, window: str, pages: int, cap: int) -> list[int]:
    """Collect movie IDs from trending endpoint for day/week windows."""
    ids: list[int] = []
    for page in range(1, max(1, pages) + 1):
        payload = _tmdb_get(api_key, f"/trending/movie/{window}", {"page": page})
        results = payload.get("results") or []
        if not results:
            break
        for row in results:
            mid = row.get("id")
            if isinstance(mid, int):
                ids.append(mid)
                if len(ids) >= cap:
                    return ids
    return ids


def _discover_page(
    api_key: str,
    *,
    base_params: dict[str, Any],
    page: int,
) -> tuple[list[int], int]:
    """Fetch one discover page and return IDs plus total_pages."""
    params = dict(base_params)
    params["page"] = page
    payload = _tmdb_get(api_key, "/discover/movie", params)
    results = payload.get("results") or []
    total_pages = int(payload.get("total_pages") or 1)
    ids = [int(row["id"]) for row in results if isinstance(row.get("id"), int)]
    return ids, max(1, total_pages)


def _trending_page(
    api_key: str,
    *,
    window: str,
    page: int,
) -> tuple[list[int], int]:
    """Fetch one trending page and return IDs plus total_pages."""
    payload = _tmdb_get(api_key, f"/trending/movie/{window}", {"page": page})
    results = payload.get("results") or []
    total_pages = int(payload.get("total_pages") or 1)
    ids = [int(row["id"]) for row in results if isinstance(row.get("id"), int)]
    return ids, max(1, total_pages)


def _build_candidate_lanes(
    api_key: str,
    *,
    max_movies: int,
    start_year: int,
    end_year: int,
    max_candidates: int,
    max_pages_per_lane: int,
    show_progress: bool = True,
    lane_bars: bool = False,
) -> dict[int, set[str]]:
    """Build a deduplicated candidate pool from multiple discover/trending lanes.

    Uses round-robin pagination over many query variants until `max_candidates`
    is reached or all lane queries are exhausted.
    """
    candidate_sources: dict[int, set[str]] = {}
    years = [y for y in range(end_year, start_year - 1, -1)]
    languages = ["en", "es", "fr", "ja", "ko", "hi", "it", "de", "pt", "zh"]
    genre_payload = _tmdb_get(api_key, "/genre/movie/list", {"language": "en-US"})
    genre_ids = [int(g["id"]) for g in (genre_payload.get("genres") or []) if isinstance(g.get("id"), int)]
    genre_ids = genre_ids[:20]

    decade_ranges: list[tuple[int, int]] = []
    decade_start = (start_year // 10) * 10
    while decade_start <= end_year:
        decade_ranges.append((decade_start, min(decade_start + 9, end_year)))
        decade_start += 10

    discover_queries: list[dict[str, Any]] = []
    for year in years:
        discover_queries.append(
            {
                "lane": "discover_popularity",
                "params": {
                    "sort_by": "popularity.desc",
                    "include_adult": "false",
                    "include_video": "false",
                    "primary_release_year": year,
                },
            }
        )
        discover_queries.append(
            {
                "lane": "discover_vote_count",
                "params": {
                    "sort_by": "vote_count.desc",
                    "include_adult": "false",
                    "include_video": "false",
                    "primary_release_year": year,
                    "vote_count.gte": 50,
                },
            }
        )
        discover_queries.append(
            {
                "lane": "discover_long_tail",
                "params": {
                    "sort_by": "popularity.desc",
                    "include_adult": "false",
                    "include_video": "false",
                    "primary_release_year": year,
                    "vote_count.gte": 20,
                    "vote_count.lte": 400,
                    "vote_average.gte": 5.5,
                },
            }
        )

    for lang in languages:
        for start, end in decade_ranges:
            discover_queries.append(
                {
                    "lane": "discover_diversity",
                    "params": {
                        "sort_by": "popularity.desc",
                        "include_adult": "false",
                        "include_video": "false",
                        "with_original_language": lang,
                        "primary_release_date.gte": f"{start}-01-01",
                        "primary_release_date.lte": f"{end}-12-31",
                        "vote_count.gte": 20,
                    },
                }
            )

    for gid in genre_ids:
        discover_queries.append(
            {
                "lane": "discover_diversity",
                "params": {
                    "sort_by": "popularity.desc",
                    "include_adult": "false",
                    "include_video": "false",
                    "with_genres": str(gid),
                    "vote_count.gte": 20,
                },
            }
        )

    discover_queries.append(
        {
            "lane": "discover_classics",
            "params": {
                "sort_by": "vote_count.desc",
                "include_adult": "false",
                "include_video": "false",
                "primary_release_date.lte": "2000-12-31",
                "vote_average.gte": 7.5,
                "vote_count.gte": 5000,
            },
        }
    )

    trending_states = [
        {"lane": "trending_day", "window": "day", "page": 1, "total_pages": None, "done": False},
        {"lane": "trending_week", "window": "week", "page": 1, "total_pages": None, "done": False},
    ]
    discover_states = [
        {
            "lane": query["lane"],
            "params": query["params"],
            "page": 1,
            "total_pages": None,
            "done": False,
        }
        for query in discover_queries
    ]

    total_page_fetches = (len(trending_states) + len(discover_states)) * int(max_pages_per_lane)
    lane_totals: dict[str, int] = {}
    for state in trending_states:
        lane_name = str(state["lane"])
        lane_totals[lane_name] = lane_totals.get(lane_name, 0) + int(max_pages_per_lane)
    for state in discover_states:
        lane_name = str(state["lane"])
        lane_totals[lane_name] = lane_totals.get(lane_name, 0) + int(max_pages_per_lane)

    interactive_lane_bars = bool(lane_bars and show_progress and sys.stderr.isatty())
    lane_progress_bars: dict[str, tqdm] = {}
    base_position = 1
    if interactive_lane_bars:
        for idx, lane_name in enumerate(sorted(lane_totals.keys())):
            lane_progress_bars[lane_name] = tqdm(
                total=max(1, lane_totals.get(lane_name, 1)),
                desc=f"Lane {lane_name}",
                unit="page",
                position=base_position + idx,
                leave=False,
            )

    lane_pbar = tqdm(
        total=max(1, total_page_fetches),
        desc="Building candidate pool",
        unit="page",
        position=0,
        disable=not show_progress,
    )
    pages_processed = 0

    # Keep cycling through all lanes and pages until we hit target or exhaust all queries.
    try:
        while len(candidate_sources) < max_candidates:
            growth_before = len(candidate_sources)

            for state in trending_states:
                if state["done"] or len(candidate_sources) >= max_candidates:
                    continue
                if int(state["page"]) > int(max_pages_per_lane):
                    state["done"] = True
                    continue
                ids, total_pages = _trending_page(api_key, window=str(state["window"]), page=int(state["page"]))
                _add_candidate(candidate_sources, ids, str(state["lane"]), max_candidates)
                state["total_pages"] = int(total_pages)
                state["page"] = int(state["page"]) + 1
                if not ids or int(state["page"]) > int(total_pages):
                    state["done"] = True
                lane_pbar.update(1)
                pages_processed += 1
                lane_name = str(state["lane"])
                if lane_name in lane_progress_bars:
                    lane_progress_bars[lane_name].update(1)
                lane_pbar.set_postfix_str(f"unique={len(candidate_sources)}")
                if (not interactive_lane_bars) and pages_processed % 100 == 0:
                    lane_counts = _lane_unique_counts(candidate_sources)
                    print(
                        f"[tmdb] lane progress pages={pages_processed}/{max(1, total_page_fetches)} "
                        f"unique={len(candidate_sources)} lanes: {_format_lane_counts(lane_counts)}",
                        flush=True,
                    )

            for state in discover_states:
                if state["done"] or len(candidate_sources) >= max_candidates:
                    continue
                if int(state["page"]) > int(max_pages_per_lane):
                    state["done"] = True
                    continue
                ids, total_pages = _discover_page(
                    api_key,
                    base_params=dict(state["params"]),
                    page=int(state["page"]),
                )
                _add_candidate(candidate_sources, ids, str(state["lane"]), max_candidates)
                state["total_pages"] = int(total_pages)
                state["page"] = int(state["page"]) + 1
                if not ids or int(state["page"]) > int(total_pages):
                    state["done"] = True
                lane_pbar.update(1)
                pages_processed += 1
                lane_name = str(state["lane"])
                if lane_name in lane_progress_bars:
                    lane_progress_bars[lane_name].update(1)
                lane_pbar.set_postfix_str(f"unique={len(candidate_sources)}")
                if (not interactive_lane_bars) and pages_processed % 100 == 0:
                    lane_counts = _lane_unique_counts(candidate_sources)
                    print(
                        f"[tmdb] lane progress pages={pages_processed}/{max(1, total_page_fetches)} "
                        f"unique={len(candidate_sources)} lanes: {_format_lane_counts(lane_counts)}",
                        flush=True,
                    )

            if len(candidate_sources) == growth_before:
                break

            has_work = any(not bool(s["done"]) for s in trending_states) or any(not bool(s["done"]) for s in discover_states)
            if not has_work:
                break
    finally:
        lane_pbar.close()
        for lane_bar in lane_progress_bars.values():
            lane_bar.close()

    lane_counts = _lane_unique_counts(candidate_sources)
    print(
        f"[tmdb] lane summary unique={len(candidate_sources)} lanes: {_format_lane_counts(lane_counts)}",
        flush=True,
    )
    return candidate_sources


def _tmdb_get(api_key: str, path: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Perform one TMDB API GET request and return parsed JSON body."""
    global _LAST_REQUEST_TS
    query = {"api_key": api_key}
    if params:
        query.update(params)
    attempts = 0
    while attempts < 5:
        if _REQUEST_MIN_INTERVAL_SECONDS > 0:
            now = time.monotonic()
            wait_for = _REQUEST_MIN_INTERVAL_SECONDS - (now - _LAST_REQUEST_TS)
            if wait_for > 0:
                time.sleep(wait_for)
        try:
            resp = requests.get(f"{TMDB_BASE_URL}{path}", params=query, timeout=30)
        except requests.exceptions.RequestException:
            # Network/TLS/transient transport errors should not abort ingest immediately.
            time.sleep(min(2.0**attempts, 15.0))
            attempts += 1
            continue
        _LAST_REQUEST_TS = time.monotonic()
        if resp.status_code == 429:
            retry_after_header = resp.headers.get("Retry-After")
            retry_after = float(retry_after_header) if retry_after_header and retry_after_header.isdigit() else 0.0
            backoff = retry_after if retry_after > 0 else min(2.0**attempts, 15.0)
            time.sleep(backoff)
            attempts += 1
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(min(2.0**attempts, 10.0))
            attempts += 1
            continue
        resp.raise_for_status()
        return resp.json()
    resp.raise_for_status()
    return {}


def _configure_request_pacing(max_rps: float) -> None:
    """Configure minimum interval between TMDB requests."""
    global _REQUEST_MIN_INTERVAL_SECONDS
    rps = max(0.1, float(max_rps))
    _REQUEST_MIN_INTERVAL_SECONDS = 1.0 / rps


async def ingest_movies(
    *,
    max_movies: int | None,
    start_year: int,
    end_year: int,
    resume: bool,
    min_vote_count: int,
    max_candidates: int,
    include_tmdb_raw: bool,
    max_rps: float,
    max_pages_per_lane: int,
    lane_bars: bool,
) -> None:
    """Ingest movies from TMDB into Postgres with resume checkpoint support."""
    from app.db import ProductRecord, get_db, init_db, settings

    api_key = (settings.tmdb_api_key or "").strip()
    if not api_key:
        raise SystemExit("TMDB_API_KEY is missing in backend/.env")
    _configure_request_pacing(max_rps=max_rps)

    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)

    checkpoint = _load_checkpoint() if resume else {}
    resume_config = {
        "start_year": int(start_year),
        "end_year": int(end_year),
        "max_candidates": int(max_candidates),
        "max_pages_per_lane": int(max_pages_per_lane),
        "min_vote_count": int(min_vote_count),
    }
    raw_candidate_ids = checkpoint.get("candidate_ids")
    raw_candidate_sources = checkpoint.get("candidate_sources")
    raw_staged_docs = checkpoint.get("staged_docs")
    raw_next_index = int(checkpoint.get("next_index", 0))
    raw_resume_config = checkpoint.get("resume_config") if isinstance(checkpoint.get("resume_config"), dict) else None
    has_resume_progress = bool(raw_next_index > 0 or raw_candidate_ids or raw_staged_docs)
    config_matches = raw_resume_config == resume_config
    can_resume = (
        checkpoint.get("strategy_version") == STRATEGY_VERSION
        and isinstance(raw_candidate_ids, list)
        and isinstance(raw_candidate_sources, dict)
        and has_resume_progress
        and config_matches
    )
    if can_resume:
        candidate_ids = [int(v) for v in (raw_candidate_ids or [])]
        candidate_sources = {
            int(mid): set(str(src) for src in sources)
            for mid, sources in (raw_candidate_sources or {}).items()
        }
        next_index = raw_next_index
        staged_docs = [dict(doc) for doc in (raw_staged_docs or []) if isinstance(doc, dict)]
    else:
        if resume and has_resume_progress:
            print("[tmdb] checkpoint parameters differ from current run; rebuilding candidate pool", flush=True)
        candidate_sources = _build_candidate_lanes(
            api_key,
            max_movies=max_movies or 0,
            start_year=start_year,
            end_year=end_year,
            max_candidates=max_candidates,
            max_pages_per_lane=max_pages_per_lane,
            lane_bars=lane_bars,
        )
        candidate_ids = list(candidate_sources.keys())
        next_index = 0
        staged_docs = []
        _save_checkpoint(
            {
                "strategy_version": STRATEGY_VERSION,
                "candidate_ids": candidate_ids,
                "candidate_sources": {str(mid): sorted(list(srcs)) for mid, srcs in candidate_sources.items()},
                "next_index": next_index,
                "staged_docs": staged_docs,
                "resume_config": resume_config,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    pbar = tqdm(total=len(candidate_ids), initial=min(next_index, len(candidate_ids)), desc="Fetching movie details")

    try:
        for idx in range(next_index, len(candidate_ids)):
            movie_id = candidate_ids[idx]
            try:
                detail = _tmdb_get(
                    api_key,
                    f"/movie/{movie_id}",
                    {"append_to_response": "credits,keywords,release_dates"},
                )
            except requests.exceptions.RequestException as exc:
                print(f"[tmdb] skipped movie_id={movie_id} after retries: {exc}")
                pbar.update(1)
                if (idx + 1) % 25 == 0:
                    _save_checkpoint(
                        {
                            "strategy_version": STRATEGY_VERSION,
                            "candidate_ids": candidate_ids,
                            "candidate_sources": {str(mid): sorted(list(srcs)) for mid, srcs in candidate_sources.items()},
                            "next_index": idx + 1,
                            "staged_docs": staged_docs,
                            "resume_config": resume_config,
                            "updated_at": datetime.now(timezone.utc).isoformat(),
                        }
                    )
                continue
            doc = _build_movie_doc(detail)
            doc["ingest_source"] = sorted(list(candidate_sources.get(movie_id, set())))
            if include_tmdb_raw:
                doc["tmdb_raw"] = detail
            if _passes_quality_filters(doc, min_vote_count=min_vote_count):
                doc["quality_score"] = round(_quality_score(doc), 6)
                staged_docs.append(doc)
            pbar.update(1)

            if (idx + 1) % 25 == 0:
                _save_checkpoint(
                    {
                        "strategy_version": STRATEGY_VERSION,
                        "candidate_ids": candidate_ids,
                        "candidate_sources": {str(mid): sorted(list(srcs)) for mid, srcs in candidate_sources.items()},
                        "next_index": idx + 1,
                        "staged_docs": staged_docs,
                        "resume_config": resume_config,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        if max_movies is None:
            selected_docs = list(staged_docs)
        else:
            selected_docs = _select_diverse_movies(staged_docs, max_movies)
        upserted = 0
        for doc in selected_docs:
            source_id = str(doc.get("source_id"))
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
                    )
                )
            upserted += 1
            if upserted % 100 == 0:
                await db.commit()
        await db.commit()
        _save_checkpoint(
            {
                "strategy_version": STRATEGY_VERSION,
                "candidate_ids": candidate_ids,
                "candidate_sources": {str(mid): sorted(list(srcs)) for mid, srcs in candidate_sources.items()},
                "next_index": len(candidate_ids),
                "staged_docs": staged_docs,
                "resume_config": resume_config,
                "selected_count": len(selected_docs),
                "upserted_count": upserted,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )
    finally:
        pbar.close()
        await db_gen.aclose()

    print(f"[tmdb] candidates fetched: {len(candidate_ids)}")
    print(f"[tmdb] quality-passing movies: {len(staged_docs)}")
    print(f"[tmdb] completed upserts: {upserted}")


def parse_args() -> argparse.Namespace:
    """Parse CLI options for TMDB ingestion."""
    parser = argparse.ArgumentParser(description="Ingest TMDB movies into Postgres")
    parser.add_argument(
        "--max-movies",
        type=int,
        default=None,
        help="Optional cap on final movies to upsert after filtering/balancing",
    )
    parser.add_argument("--start-year", type=int, default=1950, help="Earliest release year to scan")
    parser.add_argument("--end-year", type=int, default=datetime.now().year, help="Latest release year to start from")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint and start fresh")
    parser.add_argument(
        "--min-vote-count",
        type=int,
        default=MOVIE_MIN_VISIBLE_VOTE_COUNT,
        help="Hard quality filter: minimum vote_count",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=2500,
        help="Maximum candidate IDs to evaluate before diversity selection",
    )
    parser.add_argument(
        "--include-tmdb-raw",
        action="store_true",
        help="Store raw TMDB detail payload in each document under `tmdb_raw`",
    )
    parser.add_argument(
        "--max-rps",
        type=float,
        default=8.0,
        help="Maximum TMDB request rate per second (pacing + 429 backoff still applied)",
    )
    parser.add_argument(
        "--max-pages-per-lane",
        type=int,
        default=20,
        help="Maximum pages to fetch per lane query while building candidates",
    )
    parser.add_argument(
        "--lane-bars",
        action="store_true",
        help="Show additional live tqdm bars grouped by lane type (interactive terminals only)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for TMDB ingestion."""
    args = parse_args()
    asyncio.run(
        ingest_movies(
            max_movies=(max(1, int(args.max_movies)) if args.max_movies is not None else None),
            start_year=int(args.start_year),
            end_year=int(args.end_year),
            resume=not args.no_resume,
            min_vote_count=max(0, int(args.min_vote_count)),
            max_candidates=max(200, int(args.max_candidates)),
            include_tmdb_raw=bool(args.include_tmdb_raw),
            max_rps=max(0.1, float(args.max_rps)),
            max_pages_per_lane=max(1, int(args.max_pages_per_lane)),
            lane_bars=bool(args.lane_bars),
        )
    )


if __name__ == "__main__":
    main()
