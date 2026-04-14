"""
Ingest games from IGDB into Postgres products table (category=games).

Usage:
    cd backend
    python -m scripts.ingest_games_igdb --max-games 2000
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
from typing import Any, Callable

import requests
from sqlalchemy import and_, select
from tqdm import tqdm

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
CHECKPOINT_PATH = DATA_DIR / "igdb_ingest_checkpoint.json"
TWITCH_OAUTH_URL = "https://id.twitch.tv/oauth2/token"
IGDB_BASE_URL = "https://api.igdb.com/v4"
IGDB_IMAGE_BASE = "https://images.igdb.com/igdb/image/upload"
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


def _configure_request_pacing(max_rps: float) -> None:
    """Configure minimum interval between IGDB requests."""
    global _REQUEST_MIN_INTERVAL_SECONDS
    rps = max(0.1, float(max_rps))
    _REQUEST_MIN_INTERVAL_SECONDS = 1.0 / rps


def _run_pacing_sleep() -> None:
    """Respect request interval pacing to reduce rate-limit pressure."""
    global _LAST_REQUEST_TS
    if _REQUEST_MIN_INTERVAL_SECONDS <= 0:
        return
    now = time.monotonic()
    wait_for = _REQUEST_MIN_INTERVAL_SECONDS - (now - _LAST_REQUEST_TS)
    if wait_for > 0:
        time.sleep(wait_for)
    _LAST_REQUEST_TS = time.monotonic()


def _today_epoch() -> int:
    """Return UTC epoch seconds for current date/time."""
    return int(datetime.now(timezone.utc).timestamp())


def _to_date(epoch_seconds: int | None) -> str | None:
    """Convert IGDB epoch seconds into ISO date."""
    if epoch_seconds is None:
        return None
    try:
        return datetime.fromtimestamp(int(epoch_seconds), tz=timezone.utc).date().isoformat()
    except Exception:
        return None


def _decade_bucket(year: int | None) -> str | None:
    """Convert year to decade label (for example, 1990s)."""
    if year is None:
        return None
    return f"{(year // 10) * 10}s"


def _build_image_url(image_id: str | None, size: str = "t_cover_big") -> str | None:
    """Build IGDB image URL from image_id."""
    if not image_id:
        return None
    return f"{IGDB_IMAGE_BASE}/{size}/{image_id}.jpg"


def _best_vendor(game: dict[str, Any]) -> str | None:
    """Pick one canonical vendor from involved companies."""
    rows = game.get("involved_companies") or []
    if not isinstance(rows, list):
        return None
    for row in rows:
        company = row.get("company") or {}
        name = company.get("name")
        if not name:
            continue
        if bool(row.get("developer")):
            return str(name)
    for row in rows:
        company = row.get("company") or {}
        name = company.get("name")
        if name:
            return str(name)
    return None


def _build_game_doc(game: dict[str, Any]) -> dict[str, Any]:
    """Transform IGDB game payload into canonical Postgres product document."""
    source_id = str(game.get("id"))
    title = str(game.get("name") or "Untitled")
    first_release_date = int(game["first_release_date"]) if game.get("first_release_date") is not None else None
    release_date = _to_date(first_release_date)
    release_year = int(release_date[:4]) if release_date and len(release_date) >= 4 and release_date[:4].isdigit() else None

    cover_image_id = ((game.get("cover") or {}).get("image_id") if isinstance(game.get("cover"), dict) else None) or None
    images: list[dict[str, Any]] = []
    cover_url = _build_image_url(cover_image_id, size="t_cover_big")
    if cover_url:
        images.append({"url": cover_url, "alt": title, "position": 0})

    screenshot_rows = game.get("screenshots") or []
    if isinstance(screenshot_rows, list):
        for idx, row in enumerate(screenshot_rows[:3], start=1):
            image_id = row.get("image_id")
            image_url = _build_image_url(image_id, size="t_screenshot_big")
            if image_url:
                images.append({"url": image_url, "alt": title, "position": idx})

    genres = [row.get("name") for row in (game.get("genres") or []) if row.get("name")]
    themes = [row.get("name") for row in (game.get("themes") or []) if row.get("name")]
    game_modes = [row.get("name") for row in (game.get("game_modes") or []) if row.get("name")]
    perspectives = [row.get("name") for row in (game.get("player_perspectives") or []) if row.get("name")]
    keywords = [row.get("name") for row in (game.get("keywords") or []) if row.get("name")]
    platforms = [row.get("name") for row in (game.get("platforms") or []) if row.get("name")]

    companies = []
    for row in game.get("involved_companies") or []:
        company = row.get("company") or {}
        name = company.get("name")
        if name:
            companies.append(name)
    unique_companies = list(dict.fromkeys(companies))

    rating = float(game["total_rating"]) if game.get("total_rating") is not None else None
    rating_count = int(game.get("total_rating_count") or 0)
    game_status = int(game["game_status"]) if game.get("game_status") is not None else None
    hypes = int(game.get("hypes") or 0)

    return {
        "schema_version": 2,
        "source_id": source_id,
        "title": title,
        "vendor": _best_vendor(game),
        "release_year": release_year,
        "release_date": release_date,
        "total_rating": rating,
        "total_rating_count": rating_count,
        "game_status": game_status,
        "hypes": hypes,
        "has_cover": bool(cover_url),
        "decade_bucket": _decade_bucket(release_year),
        "genres": genres,
        "themes": themes,
        "game_modes": game_modes,
        "player_perspectives": perspectives,
        "keywords": keywords,
        "platforms": platforms,
        "involved_companies": unique_companies,
        "summary": game.get("summary"),
        "description": game.get("summary"),
        "url": f"https://www.igdb.com/games/{game.get('slug')}" if game.get("slug") else None,
        "images": images,
    }


def _passes_quality_filters(doc: dict[str, Any], min_rating_count: int, min_total_rating: float) -> bool:
    """Apply hard quality filters for gameplay-ready game records."""
    release_date = doc.get("release_date")
    if not release_date:
        return False
    if release_date > datetime.now(timezone.utc).date().isoformat():
        return False
    if not doc.get("has_cover"):
        return False
    if len(doc.get("genres") or []) == 0:
        return False
    if len(doc.get("platforms") or []) == 0:
        return False
    if int(doc.get("total_rating_count") or 0) < int(min_rating_count):
        return False
    if float(doc.get("total_rating") or 0.0) < float(min_total_rating):
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
    return max(0.0, min(1.0, 1.0 - age / 25.0))


def _quality_score(doc: dict[str, Any]) -> float:
    """Compute weighted soft quality score for ranking candidates."""
    rating_count = max(0, int(doc.get("total_rating_count") or 0))
    rating = max(0.0, min(100.0, float(doc.get("total_rating") or 0.0)))
    hypes = max(0.0, float(doc.get("hypes") or 0.0))
    recency = _recency_bonus(doc.get("release_year"))
    return (
        0.40 * (rating / 10.0)
        + 0.30 * math.log1p(rating_count)
        + 0.20 * math.log1p(hypes)
        + 0.10 * recency
    )


def _primary_genre(doc: dict[str, Any]) -> str:
    """Return one canonical genre for diversity balancing."""
    genres = doc.get("genres") or []
    if not genres:
        return "unknown"
    return str(genres[0]).strip().lower() or "unknown"


def _primary_platform(doc: dict[str, Any]) -> str:
    """Return one canonical platform for diversity balancing."""
    platforms = doc.get("platforms") or []
    if not platforms:
        return "unknown"
    return str(platforms[0]).strip().lower() or "unknown"


def _select_diverse_games(candidates: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
    """Select top games with soft quota balancing by decade/genre/platform."""
    if target <= 0 or not candidates:
        return []
    pool = list(candidates)
    selected: list[dict[str, Any]] = []
    count_decade: dict[str, int] = {}
    count_genre: dict[str, int] = {}
    count_platform: dict[str, int] = {}
    decade_target = max(1, int(target * 0.20))
    genre_target = max(1, int(target * 0.14))
    platform_target = max(1, int(target * 0.18))

    classic_target = max(1, int(target * 0.12))
    classic_candidates = [
        doc
        for doc in pool
        if (doc.get("release_year") or 9999) <= 2005
        and int(doc.get("total_rating_count") or 0) >= 200
        and float(doc.get("total_rating") or 0.0) >= 80.0
    ]
    classic_candidates.sort(key=lambda d: float(d.get("quality_score") or 0.0), reverse=True)
    for doc in classic_candidates[:classic_target]:
        selected.append(doc)
        if doc in pool:
            pool.remove(doc)
        decade = str(doc.get("decade_bucket") or "unknown")
        genre = _primary_genre(doc)
        platform = _primary_platform(doc)
        count_decade[decade] = count_decade.get(decade, 0) + 1
        count_genre[genre] = count_genre.get(genre, 0) + 1
        count_platform[platform] = count_platform.get(platform, 0) + 1

    while pool and len(selected) < target:
        best_idx = 0
        best_score = float("-inf")
        for idx, doc in enumerate(pool):
            decade = str(doc.get("decade_bucket") or "unknown")
            genre = _primary_genre(doc)
            platform = _primary_platform(doc)
            penalty = (
                0.35 * (count_decade.get(decade, 0) / decade_target)
                + 0.40 * (count_genre.get(genre, 0) / genre_target)
                + 0.25 * (count_platform.get(platform, 0) / platform_target)
            )
            adjusted = float(doc.get("quality_score") or 0.0) - penalty
            if adjusted > best_score:
                best_score = adjusted
                best_idx = idx
        chosen = pool.pop(best_idx)
        selected.append(chosen)
        chosen_decade = str(chosen.get("decade_bucket") or "unknown")
        chosen_genre = _primary_genre(chosen)
        chosen_platform = _primary_platform(chosen)
        count_decade[chosen_decade] = count_decade.get(chosen_decade, 0) + 1
        count_genre[chosen_genre] = count_genre.get(chosen_genre, 0) + 1
        count_platform[chosen_platform] = count_platform.get(chosen_platform, 0) + 1
    return selected


def _add_candidate(
    candidate_sources: dict[int, set[str]],
    ids: list[int],
    lane: str,
    cap: int,
) -> None:
    """Append IDs into candidate map while preserving insertion order."""
    for gid in ids:
        if len(candidate_sources) >= cap and gid not in candidate_sources:
            break
        candidate_sources.setdefault(gid, set()).add(lane)


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


def _twitch_access_token(client_id: str, client_secret: str) -> str:
    """Fetch app access token from Twitch OAuth."""
    resp = requests.post(
        TWITCH_OAUTH_URL,
        params={
            "client_id": client_id,
            "client_secret": client_secret,
            "grant_type": "client_credentials",
        },
        timeout=30,
    )
    resp.raise_for_status()
    payload = resp.json()
    token = str(payload.get("access_token") or "").strip()
    if not token:
        raise RuntimeError("Unable to obtain Twitch OAuth access token for IGDB")
    return token


def _igdb_request(
    *,
    client_id: str,
    access_token: str,
    endpoint: str,
    query: str,
) -> list[dict[str, Any]]:
    """Execute one IGDB APICalypse request with retries."""
    attempts = 0
    last_error: Exception | None = None
    headers = {
        "Client-ID": client_id,
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
    }
    while attempts < 6:
        _run_pacing_sleep()
        try:
            resp = requests.post(
                f"{IGDB_BASE_URL}/{endpoint}",
                headers=headers,
                data=query.encode("utf-8"),
                timeout=45,
            )
        except requests.exceptions.RequestException as exc:
            last_error = exc
            time.sleep(min(2.0**attempts, 20.0))
            attempts += 1
            continue
        if resp.status_code == 429:
            retry_after_header = resp.headers.get("Retry-After")
            retry_after = float(retry_after_header) if retry_after_header and retry_after_header.isdigit() else 0.0
            backoff = retry_after if retry_after > 0 else min(2.0**attempts, 20.0)
            time.sleep(backoff)
            attempts += 1
            continue
        if 500 <= resp.status_code < 600:
            time.sleep(min(2.0**attempts, 15.0))
            attempts += 1
            continue
        if 400 <= resp.status_code < 500:
            body_preview = (resp.text or "").strip().replace("\n", " ")
            if len(body_preview) > 300:
                body_preview = f"{body_preview[:300]}..."
            raise requests.exceptions.HTTPError(
                f"{resp.status_code} Client Error for url: {resp.url} | body={body_preview}",
                response=resp,
            )
        resp.raise_for_status()
        payload = resp.json()
        if isinstance(payload, list):
            return payload
        return []
    if last_error is not None:
        raise last_error
    raise RuntimeError("IGDB request failed after retries")
    return []


def _query_ids(
    *,
    client_id: str,
    access_token: str,
    where_clause: str,
    sort_clause: str,
    pages: int,
    cap: int,
    page_size: int = 500,
    on_page: Callable[[], None] | None = None,
) -> list[int]:
    """Collect game IDs from one APICalypse lane query."""
    ids: list[int] = []
    for page in range(max(1, pages)):
        offset = page * page_size
        query = (
            "fields id;"
            f" where {where_clause};"
            f" sort {sort_clause};"
            f" limit {page_size};"
            f" offset {offset};"
        )
        rows = _igdb_request(client_id=client_id, access_token=access_token, endpoint="games", query=query)
        if on_page is not None:
            on_page()
        if not rows:
            break
        for row in rows:
            gid = row.get("id")
            if isinstance(gid, int):
                ids.append(gid)
                if len(ids) >= cap:
                    return ids
    return ids


def _build_candidate_lanes(
    *,
    client_id: str,
    access_token: str,
    start_year: int,
    end_year: int,
    max_candidates: int,
    max_pages_per_lane: int,
    lane_bars: bool = False,
) -> dict[int, set[str]]:
    """Build deduplicated candidate pool from multiple IGDB lanes."""
    candidate_sources: dict[int, set[str]] = {}
    now_epoch = _today_epoch()
    start_epoch = int(datetime(start_year, 1, 1, tzinfo=timezone.utc).timestamp())
    end_epoch = int(datetime(end_year, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    allowed_game_types = "(0,4,8,9,10,11)"
    lane_cap = max(1, max_candidates // 3)
    # Scale lane depth from the historical baseline (primary=6, secondary=4, decade=1)
    # so default behavior stays unchanged while larger values broaden coverage.
    scale = max(1.0 / 6.0, float(max_pages_per_lane) / 6.0)
    primary_pages = max(1, int(math.ceil(6 * scale)))
    secondary_pages = max(1, int(math.ceil(4 * scale)))
    decade_pages = max(1, int(math.ceil(1 * scale)))
    decade_start = (start_year // 10) * 10
    decade_lane_count = 0
    while decade_start <= end_year:
        decade_lane_count += 1
        decade_start += 10
    lane_totals = {
        "popular_hype": primary_pages,
        "popular_rating_count": primary_pages,
        "high_rated": primary_pages,
        "recent_hype": secondary_pages,
        "long_tail_quality": secondary_pages,
        "decade_balance": max(1, decade_lane_count) * decade_pages,
        "classics": primary_pages,
    }
    total_page_fetches = sum(lane_totals.values())
    interactive_lane_bars = bool(lane_bars and sys.stderr.isatty())
    lane_progress_bars: dict[str, tqdm] = {}
    if interactive_lane_bars:
        for idx, lane_name in enumerate(sorted(lane_totals.keys())):
            lane_progress_bars[lane_name] = tqdm(
                total=max(1, lane_totals.get(lane_name, 1)),
                desc=f"Lane {lane_name}",
                unit="page",
                position=1 + idx,
                leave=False,
            )

    lane_pbar = tqdm(
        total=max(1, total_page_fetches),
        desc="Building candidate pool",
        unit="page",
        position=0,
    )
    pages_processed = 0

    def _on_page(lane_name: str) -> None:
        nonlocal pages_processed
        lane_pbar.update(1)
        pages_processed += 1
        if lane_name in lane_progress_bars:
            lane_progress_bars[lane_name].update(1)
        lane_pbar.set_postfix_str(f"unique={len(candidate_sources)}")
        if (not interactive_lane_bars) and pages_processed % 25 == 0:
            lane_counts = _lane_unique_counts(candidate_sources)
            print(
                f"[igdb] lane progress pages={pages_processed}/{max(1, total_page_fetches)} "
                f"unique={len(candidate_sources)} lanes: {_format_lane_counts(lane_counts)}",
                flush=True,
            )

    base = (
        "version_parent = null"
        " & first_release_date != null"
        f" & first_release_date >= {start_epoch}"
        f" & first_release_date <= {min(end_epoch, now_epoch)}"
        f" & game_type = {allowed_game_types}"
    )

    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=f"{base} & total_rating_count >= 25 & hypes >= 1",
            sort_clause="hypes desc",
            pages=primary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("popular_hype"),
        ),
        "popular_hype",
        max_candidates,
    )

    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=f"{base} & total_rating_count >= 40",
            sort_clause="total_rating_count desc",
            pages=primary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("popular_rating_count"),
        ),
        "popular_rating_count",
        max_candidates,
    )

    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=f"{base} & total_rating_count >= 40 & total_rating >= 70",
            sort_clause="total_rating desc",
            pages=primary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("high_rated"),
        ),
        "high_rated",
        max_candidates,
    )

    recent_2y_epoch = int(
        datetime(datetime.now(timezone.utc).year - 2, 1, 1, tzinfo=timezone.utc).timestamp()
    )
    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=f"{base} & first_release_date >= {recent_2y_epoch} & hypes >= 5",
            sort_clause="hypes desc",
            pages=secondary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("recent_hype"),
        ),
        "recent_hype",
        max_candidates,
    )

    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=f"{base} & total_rating_count >= 10 & total_rating_count <= 250 & total_rating >= 72",
            sort_clause="total_rating desc",
            pages=secondary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("long_tail_quality"),
        ),
        "long_tail_quality",
        max_candidates,
    )

    decade_start = (start_year // 10) * 10
    while decade_start <= end_year and len(candidate_sources) < max_candidates:
        decade_end = min(decade_start + 9, end_year)
        decade_start_epoch = int(datetime(decade_start, 1, 1, tzinfo=timezone.utc).timestamp())
        decade_end_epoch = int(datetime(decade_end, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
        _add_candidate(
            candidate_sources,
            _query_ids(
                client_id=client_id,
                access_token=access_token,
                where_clause=(
                    f"{base} & first_release_date >= {decade_start_epoch}"
                    f" & first_release_date <= {min(decade_end_epoch, now_epoch)}"
                    " & total_rating_count >= 15"
                ),
                sort_clause="total_rating_count desc",
                pages=decade_pages,
                cap=lane_cap,
                on_page=lambda: _on_page("decade_balance"),
            ),
            "decade_balance",
            max_candidates,
        )
        decade_start += 10

    classics_end_epoch = int(datetime(2005, 12, 31, 23, 59, 59, tzinfo=timezone.utc).timestamp())
    _add_candidate(
        candidate_sources,
        _query_ids(
            client_id=client_id,
            access_token=access_token,
            where_clause=(
                "version_parent = null"
                " & first_release_date != null"
                f" & first_release_date <= {classics_end_epoch}"
                f" & game_type = {allowed_game_types}"
                " & total_rating_count >= 200"
                " & total_rating >= 80"
            ),
            sort_clause="total_rating_count desc",
            pages=primary_pages,
            cap=lane_cap,
            on_page=lambda: _on_page("classics"),
        ),
        "classics",
        max_candidates,
    )
    lane_pbar.close()
    for lane_bar in lane_progress_bars.values():
        lane_bar.close()
    lane_counts = _lane_unique_counts(candidate_sources)
    print(
        f"[igdb] lane summary unique={len(candidate_sources)} lanes: {_format_lane_counts(lane_counts)}",
        flush=True,
    )
    return candidate_sources


def _detail_query(ids: list[int]) -> str:
    """Build games detail APICalypse query for one ID batch."""
    id_csv = ",".join(str(v) for v in ids)
    return (
        "fields "
        "id,name,slug,summary,first_release_date,game_type,game_status,"
        "total_rating,total_rating_count,rating,rating_count,aggregated_rating,aggregated_rating_count,"
        "hypes,"
        "cover.image_id,screenshots.image_id,"
        "genres.name,themes.name,game_modes.name,player_perspectives.name,platforms.name,keywords.name,"
        "involved_companies.developer,involved_companies.publisher,involved_companies.company.name;"
        f" where id = ({id_csv});"
        " limit 500;"
    )


async def ingest_games(
    *,
    max_games: int | None,
    start_year: int,
    end_year: int,
    resume: bool,
    min_rating_count: int,
    min_total_rating: float,
    max_candidates: int,
    max_pages_per_lane: int,
    include_igdb_raw: bool,
    max_rps: float,
    detail_batch_size: int,
    lane_bars: bool,
) -> None:
    """Ingest games from IGDB into Postgres with resume checkpoint support."""
    from app.db import ProductRecord, get_db, init_db, settings

    client_id = (settings.igdb_client_id or "").strip()
    client_secret = (settings.igdb_client_secret or "").strip()
    if not client_id or not client_secret:
        raise SystemExit("IGDB_CLIENT_ID or IGDB_CLIENT_SECRET is missing in backend/.env")
    _configure_request_pacing(max_rps=max_rps)
    access_token = _twitch_access_token(client_id, client_secret)

    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)

    checkpoint = _load_checkpoint() if resume else {}
    resume_config = {
        "start_year": int(start_year),
        "end_year": int(end_year),
        "max_candidates": int(max_candidates),
        "max_pages_per_lane": int(max_pages_per_lane),
        "min_rating_count": int(min_rating_count),
        "min_total_rating": float(min_total_rating),
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
            int(gid): set(str(src) for src in sources)
            for gid, sources in (raw_candidate_sources or {}).items()
        }
        next_index = raw_next_index
        staged_docs = [dict(doc) for doc in (raw_staged_docs or []) if isinstance(doc, dict)]
    else:
        if resume and has_resume_progress:
            print("[igdb] checkpoint parameters differ from current run; rebuilding candidate pool", flush=True)
        candidate_sources = _build_candidate_lanes(
            client_id=client_id,
            access_token=access_token,
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
                "candidate_sources": {str(gid): sorted(list(srcs)) for gid, srcs in candidate_sources.items()},
                "next_index": next_index,
                "staged_docs": staged_docs,
                "resume_config": resume_config,
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    pbar = tqdm(total=len(candidate_ids), initial=min(next_index, len(candidate_ids)), desc="Fetching game details")

    try:
        idx = next_index
        while idx < len(candidate_ids):
            batch_ids = candidate_ids[idx : idx + detail_batch_size]
            try:
                rows = _igdb_request(
                    client_id=client_id,
                    access_token=access_token,
                    endpoint="games",
                    query=_detail_query(batch_ids),
                )
            except requests.exceptions.RequestException as exc:
                print(f"[igdb] skipped batch starting_at={idx} after retries: {exc}")
                idx += len(batch_ids)
                pbar.update(len(batch_ids))
                continue

            by_id: dict[int, dict[str, Any]] = {}
            for row in rows:
                gid = row.get("id")
                if isinstance(gid, int):
                    by_id[gid] = row

            for gid in batch_ids:
                detail = by_id.get(gid)
                if detail is None:
                    pbar.update(1)
                    continue
                doc = _build_game_doc(detail)
                doc["ingest_source"] = sorted(list(candidate_sources.get(gid, set())))
                if include_igdb_raw:
                    doc["igdb_raw"] = detail
                if _passes_quality_filters(
                    doc,
                    min_rating_count=min_rating_count,
                    min_total_rating=min_total_rating,
                ):
                    doc["quality_score"] = round(_quality_score(doc), 6)
                    staged_docs.append(doc)
                pbar.update(1)

            idx += len(batch_ids)
            if idx % 50 == 0:
                _save_checkpoint(
                    {
                        "strategy_version": STRATEGY_VERSION,
                        "candidate_ids": candidate_ids,
                        "candidate_sources": {str(gid): sorted(list(srcs)) for gid, srcs in candidate_sources.items()},
                        "next_index": idx,
                        "staged_docs": staged_docs,
                        "resume_config": resume_config,
                        "updated_at": datetime.now(timezone.utc).isoformat(),
                    }
                )

        if max_games is None:
            selected_docs = list(staged_docs)
        else:
            selected_docs = _select_diverse_games(staged_docs, max_games)
        upserted = 0
        for doc in selected_docs:
            source_id = str(doc.get("source_id"))
            existing = await db.scalar(
                select(ProductRecord).where(
                    and_(
                        ProductRecord.category == "games",
                        ProductRecord.data["source_id"].as_string() == source_id,
                    )
                )
            )
            if existing:
                existing.data = doc
            else:
                db.add(
                    ProductRecord(
                        category="games",
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
                "candidate_sources": {str(gid): sorted(list(srcs)) for gid, srcs in candidate_sources.items()},
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

    print(f"[igdb] candidates fetched: {len(candidate_ids)}")
    print(f"[igdb] quality-passing games: {len(staged_docs)}")
    print(f"[igdb] completed upserts: {upserted}")


def parse_args() -> argparse.Namespace:
    """Parse CLI options for IGDB ingestion."""
    parser = argparse.ArgumentParser(description="Ingest IGDB games into Postgres")
    parser.add_argument(
        "--max-games",
        type=int,
        default=None,
        help="Optional cap on final games to upsert after filtering/balancing",
    )
    parser.add_argument("--start-year", type=int, default=1980, help="Earliest release year to scan")
    parser.add_argument("--end-year", type=int, default=datetime.now().year, help="Latest release year to start from")
    parser.add_argument("--no-resume", action="store_true", help="Ignore checkpoint and start fresh")
    parser.add_argument("--min-rating-count", type=int, default=20, help="Hard quality filter: minimum rating count")
    parser.add_argument(
        "--min-total-rating",
        type=float,
        default=60.0,
        help="Hard quality filter: minimum total rating (0-100 scale)",
    )
    parser.add_argument(
        "--max-candidates",
        type=int,
        default=5000,
        help="Maximum candidate IDs to evaluate before diversity selection",
    )
    parser.add_argument(
        "--max-pages-per-lane",
        type=int,
        default=20,
        help="Maximum pages to fetch per lane query while building candidates",
    )
    parser.add_argument(
        "--include-igdb-raw",
        action="store_true",
        help="Store raw IGDB detail payload in each document under `igdb_raw`",
    )
    parser.add_argument(
        "--max-rps",
        type=float,
        default=4.0,
        help="Maximum IGDB request rate per second (pacing + 429 backoff still applied)",
    )
    parser.add_argument(
        "--detail-batch-size",
        type=int,
        default=100,
        help="Number of game IDs per details query batch",
    )
    parser.add_argument(
        "--lane-bars",
        action="store_true",
        help="Show additional live tqdm bars grouped by lane type (interactive terminals only)",
    )
    return parser.parse_args()


def main() -> None:
    """CLI entrypoint for IGDB ingestion."""
    args = parse_args()
    asyncio.run(
        ingest_games(
            max_games=(max(1, int(args.max_games)) if args.max_games is not None else None),
            start_year=int(args.start_year),
            end_year=int(args.end_year),
            resume=not args.no_resume,
            min_rating_count=max(0, int(args.min_rating_count)),
            min_total_rating=max(0.0, min(100.0, float(args.min_total_rating))),
            max_candidates=max(500, int(args.max_candidates)),
            max_pages_per_lane=max(1, int(args.max_pages_per_lane)),
            include_igdb_raw=bool(args.include_igdb_raw),
            max_rps=max(0.1, float(args.max_rps)),
            detail_batch_size=max(20, min(500, int(args.detail_batch_size))),
            lane_bars=bool(args.lane_bars),
        )
    )


if __name__ == "__main__":
    main()
