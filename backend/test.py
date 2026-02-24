"""
Lightweight local database utility for the Postgres-backed store.

Usage:
    python test.py summary
    python test.py list-collections
    python test.py clear-games
"""

from __future__ import annotations

import argparse
import asyncio

from app.db import (
    GameRecord,
    GameRoundRecord,
    PrefixRatingRecord,
    ProductRecord,
    UserRecord,
    get_db,
    init_db,
)
from sqlalchemy import delete, func, select


async def list_collections() -> None:
    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)
    print("Tables:")
    for name in ["products", "users", "games", "game_rounds", "prefix_ratings"]:
        print(f"  - {name}")
    await db_gen.aclose()


async def summary() -> None:
    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)
    product_total = int(await db.scalar(select(func.count()).select_from(ProductRecord)) or 0)
    pen_count = int(
        await db.scalar(select(func.count()).select_from(ProductRecord).where(ProductRecord.category == "fountain_pens"))
        or 0
    )
    movie_count = int(
        await db.scalar(select(func.count()).select_from(ProductRecord).where(ProductRecord.category == "movies")) or 0
    )
    counts = {
        "products_total": product_total,
        "products_fountain_pens": pen_count,
        "products_movies": movie_count,
        "users": int(await db.scalar(select(func.count()).select_from(UserRecord)) or 0),
        "games": int(await db.scalar(select(func.count()).select_from(GameRecord)) or 0),
        "game_rounds": int(await db.scalar(select(func.count()).select_from(GameRoundRecord)) or 0),
        "prefix_ratings": int(await db.scalar(select(func.count()).select_from(PrefixRatingRecord)) or 0),
    }
    total = 0
    for name, count in counts.items():
        total += count
        print(f"{name}: {count}")
    print(f"TOTAL: {total-product_total}")
    await db_gen.aclose()


async def clear_games() -> None:
    """Delete all game-related rows (games, rounds, prefix ratings)."""
    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)
    deleted_rounds = await db.execute(delete(GameRoundRecord))
    deleted_games = await db.execute(delete(GameRecord))
    deleted_prefix = await db.execute(delete(PrefixRatingRecord))
    await db.commit()
    print(f"deleted game_rounds: {int(deleted_rounds.rowcount or 0)}")
    print(f"deleted games: {int(deleted_games.rowcount or 0)}")
    print(f"deleted prefix_ratings: {int(deleted_prefix.rowcount or 0)}")
    await db_gen.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postgres local DB utility")
    parser.add_argument(
        "command",
        choices=["summary", "list-collections", "clear-games"],
        help="Operation to run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "summary":
        asyncio.run(summary())
    elif args.command == "clear-games":
        asyncio.run(clear_games())
    else:
        asyncio.run(list_collections())


if __name__ == "__main__":
    main()
