"""Shared visibility rules for category catalogs."""

from __future__ import annotations

from typing import Any

MOVIE_MIN_VISIBLE_VOTE_COUNT = 1000


def movie_is_visible(product: dict[str, Any], *, min_vote_count: int = MOVIE_MIN_VISIBLE_VOTE_COUNT) -> bool:
    """Return whether a movie meets the app's vote-count visibility threshold."""
    try:
        vote_count = int(product.get("vote_count") or 0)
    except (TypeError, ValueError):
        vote_count = 0
    return vote_count >= int(min_vote_count)
