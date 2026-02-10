"""
Load fountain pen data from backend/data/products.json.

Defaults to MongoDB (the active backend used by start.bat and app.main_mongo).

Usage:
    cd backend
    python -m scripts.load_db                  # load pens into MongoDB
    python -m scripts.load_db --target sqlite  # legacy SQLite loader
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


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
        "category": "fountain_pens",
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
        "created_at": datetime.now(timezone.utc),
    }


def load_products_mongo(replace: bool = True) -> None:
    from pymongo import MongoClient
    from app.db_mongo import settings

    data = _read_products()
    source_ids = [item.get("source_id") for item in data if item.get("source_id")]

    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]
    products = db.products

    # Keep movies/other categories intact. Reset only fountain-pen docs
    # and any legacy docs with matching source_ids.
    if replace:
        delete_filter = {
            "$or": [
                {"category": "fountain_pens"},
                {"source_id": {"$in": source_ids}},
            ]
        }
        deleted = products.delete_many(delete_filter).deleted_count
        print(f"[mongo] removed {deleted} existing pen docs")

    upserts = 0
    for item in data:
        source_id = item.get("source_id")
        if not source_id:
            continue
        doc = _normalized_pen_doc(item)
        products.update_one(
            {"category": "fountain_pens", "source_id": source_id},
            {"$set": doc},
            upsert=True,
        )
        upserts += 1

    products.create_index([("category", 1), ("source_id", 1)], unique=True)
    products.create_index([("category", 1), ("title", 1)])
    products.create_index([("category", 1), ("vendor", 1)])

    total_pens = products.count_documents({"category": "fountain_pens"})
    total_movies = products.count_documents({"category": "movies"})
    print(f"[mongo] upserted {upserts} fountain pen docs")
    print(f"[mongo] totals -> pens: {total_pens}, movies: {total_movies}")
    client.close()


def load_products_sqlite() -> None:
    # Legacy loader kept for compatibility with old SQLite backend.
    from sqlalchemy.orm import Session
    from app.db import Base, engine, SessionLocal
    from app.models import Product, ProductImage

    data = _read_products()

    def _load(db: Session) -> None:
        db.query(ProductImage).delete()
        db.query(Product).delete()
        db.commit()

        for item in data:
            product = Product(
                source_id=item.get("source_id"),
                title=item.get("title"),
                handle=item.get("handle"),
                vendor=item.get("vendor"),
                product_type=item.get("product_type"),
                price_min=item.get("price_min"),
                price_max=item.get("price_max"),
                currency=item.get("currency"),
                tags_json=json.dumps(item.get("tags", [])),
                options_json=json.dumps(item.get("options", {})),
                description=item.get("description"),
                url=item.get("url"),
            )
            db.add(product)
            db.flush()
            for img in item.get("images", []):
                db.add(
                    ProductImage(
                        product_id=product.id,
                        url=img.get("url"),
                        alt=img.get("alt"),
                        position=img.get("position"),
                    )
                )
        db.commit()

    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        _load(db)
    print("[sqlite] loaded products into SQLite database")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Load fountain pen products")
    parser.add_argument(
        "--target",
        choices=["mongo", "sqlite"],
        default="mongo",
        help="Database target (default: mongo)",
    )
    parser.add_argument(
        "--no-replace",
        action="store_true",
        help="Do not remove existing fountain pen docs before upsert (mongo only)",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.target == "mongo":
        load_products_mongo(replace=not args.no_replace)
    else:
        load_products_sqlite()


if __name__ == "__main__":
    main()
