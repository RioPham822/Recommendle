"""
Lightweight local database utility for the Postgres-backed store.

Usage:
    python test.py summary
    python test.py list-collections
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
from sqlalchemy import func, select


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
    counts = {
        "products": int(await db.scalar(select(func.count()).select_from(ProductRecord)) or 0),
        "users": int(await db.scalar(select(func.count()).select_from(UserRecord)) or 0),
        "games": int(await db.scalar(select(func.count()).select_from(GameRecord)) or 0),
        "game_rounds": int(await db.scalar(select(func.count()).select_from(GameRoundRecord)) or 0),
        "prefix_ratings": int(await db.scalar(select(func.count()).select_from(PrefixRatingRecord)) or 0),
    }
    total = 0
    for name, count in counts.items():
        total += count
        print(f"{name}: {count}")
    print(f"TOTAL: {total}")
    await db_gen.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Postgres local DB utility")
    parser.add_argument(
        "command",
        choices=["summary", "list-collections"],
        help="Operation to run",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "summary":
        asyncio.run(summary())
    else:
        asyncio.run(list_collections())


if __name__ == "__main__":
    main()
