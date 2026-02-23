"""
Load fountain pen data from backend/data/products.json into Postgres-backed store.

Defaults to the active Postgres backend used by app.main.

Usage:
    cd backend
    python -m scripts.load_db                  # load pens
    python -m scripts.load_db --no-replace     # load without removing existing
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from tqdm import tqdm
from sqlalchemy import and_, delete, func, select

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

DATA_DIR = ROOT_DIR / "data"
PRODUCTS_JSON = DATA_DIR / "products.json"


def _read_products() -> list[dict[str, Any]]:
    if not PRODUCTS_JSON.exists():
        raise SystemExit("products.json not found. Run scrape_gouletpens.py first.")
    return json.loads(PRODUCTS_JSON.read_text(encoding="utf-8"))


def _normalized_pen_doc(item: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": 2,
        "source_id": item.get("source_id"),
        "title": item.get("title"),
        "handle": item.get("handle"),
        "vendor": item.get("vendor"),
        "product_type": item.get("product_type"),
        "price_min": item.get("price_min"),
        "price_max": item.get("price_max"),
        "currency": item.get("currency"),
        "tags": item.get("tags", []),
        "options": item.get("options", {}),
        "description": item.get("description"),
        "url": item.get("url"),
        "images": item.get("images", []),
    }


async def load_products(replace: bool = True) -> None:
    from app.db import ProductRecord, get_db, init_db

    data = _read_products()
    source_ids = [item.get("source_id") for item in data if item.get("source_id")]
    await init_db()
    db_gen = get_db()
    db = await anext(db_gen)

    # Keep movies/other categories intact. Reset only fountain-pen docs
    # and any legacy docs with matching source_ids.
    if replace:
        deleted_result = await db.execute(
            delete(ProductRecord).where(
                (ProductRecord.category == "fountain_pens")
                | (ProductRecord.data["source_id"].as_string().in_(source_ids))
            )
        )
        await db.commit()
        deleted = int(deleted_result.rowcount or 0)
        print(f"[postgres] removed {deleted} existing pen docs")

    upserts = 0
    for item in tqdm(data):
        source_id = item.get("source_id")
        if not source_id:
            continue
        doc = _normalized_pen_doc(item)
        existing = await db.scalar(
            select(ProductRecord).where(
                and_(
                    ProductRecord.category == "fountain_pens",
                    ProductRecord.data["source_id"].as_string() == source_id,
                )
            )
        )
        if existing:
            existing.data = doc
        else:
            db.add(
                ProductRecord(
                    category="fountain_pens",
                    data=doc,
                    created_at=datetime.now(timezone.utc),
                )
            )
        upserts += 1

    await db.commit()

    total_pens = await db.scalar(select(func.count()).select_from(ProductRecord).where(ProductRecord.category == "fountain_pens"))
    total_movies = await db.scalar(select(func.count()).select_from(ProductRecord).where(ProductRecord.category == "movies"))
    print(f"[postgres] upserted {upserts} fountain pen docs")
    print(f"[postgres] totals -> pens: {int(total_pens or 0)}, movies: {int(total_movies or 0)}")
    await db_gen.aclose()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load fountain pen products into Postgres store")
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Do not remove existing fountain pen docs before upsert",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    asyncio.run(load_products(replace=not args.no_replace))


if __name__ == "__main__":
    main()
