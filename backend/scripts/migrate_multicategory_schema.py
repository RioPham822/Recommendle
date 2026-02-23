"""
Forward migration for multi-category support.

Usage:
    cd backend
    python -m scripts.migrate_multicategory_schema
"""
from __future__ import annotations

import shutil
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from bson.json_util import dumps
from pymongo import MongoClient

from app.db import settings


ROOT_DIR = Path(__file__).resolve().parents[1]
BACKUP_DIR = ROOT_DIR / "backups"
COLLECTIONS_TO_BACKUP = [
    "products",
    "users",
    "sessions",
    "selections",
    "prefix_ratings",
    "games",
    "game_rounds",
]


def _timestamp() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")


def backup_database(db_name: str) -> Path:
    backup_path = BACKUP_DIR / f"multicategory_{_timestamp()}"
    backup_path.mkdir(parents=True, exist_ok=True)

    mongodump = shutil.which("mongodump")
    if mongodump:
        try:
            subprocess.run(
                [
                    mongodump,
                    "--uri",
                    settings.mongodb_url,
                    "--db",
                    db_name,
                    "--out",
                    str(backup_path),
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            print(f"[backup] mongodump completed: {backup_path}")
            return backup_path
        except subprocess.CalledProcessError as exc:
            print(f"[backup] mongodump failed, falling back to JSON export: {exc.stderr}")

    client = MongoClient(settings.mongodb_url)
    db = client[db_name]
    for name in COLLECTIONS_TO_BACKUP:
        docs = list(db[name].find())
        (backup_path / f"{name}.json").write_text(dumps(docs, indent=2), encoding="utf-8")
    client.close()
    print(f"[backup] JSON fallback completed: {backup_path}")
    return backup_path


def normalize_reference_types(db) -> None:
    # sessions.user_id -> string
    for doc in db.sessions.find({"user_id": {"$type": "objectId"}}, {"user_id": 1}):
        db.sessions.update_one({"_id": doc["_id"]}, {"$set": {"user_id": str(doc["user_id"])}})

    # selections: session_id/product_id -> string
    for doc in db.selections.find({"session_id": {"$type": "objectId"}}, {"session_id": 1}):
        db.selections.update_one({"_id": doc["_id"]}, {"$set": {"session_id": str(doc["session_id"])}})
    for doc in db.selections.find({"product_id": {"$type": "objectId"}}, {"product_id": 1}):
        db.selections.update_one({"_id": doc["_id"]}, {"$set": {"product_id": str(doc["product_id"])}})

    # prefix_ratings.session_id -> string
    for doc in db.prefix_ratings.find({"session_id": {"$type": "objectId"}}, {"session_id": 1}):
        db.prefix_ratings.update_one({"_id": doc["_id"]}, {"$set": {"session_id": str(doc["session_id"])}})

    # users.sessions[] -> string list
    for doc in db.users.find({"sessions.0": {"$exists": True}}, {"sessions": 1}):
        sessions = doc.get("sessions", [])
        normalized = [str(item) for item in sessions]
        if normalized != sessions:
            db.users.update_one({"_id": doc["_id"]}, {"$set": {"sessions": normalized}})


def migrate_products(db) -> None:
    result = db.products.update_many(
        {"category": {"$exists": False}},
        {"$set": {"category": "fountain_pens"}},
    )
    print(f"[products] category backfilled: {result.modified_count}")

    # Ensure all docs carry a schema marker for debugging/audits.
    result = db.products.update_many(
        {"schema_version": {"$exists": False}},
        {"$set": {"schema_version": 2}},
    )
    print(f"[products] schema_version set: {result.modified_count}")


def migrate_games(db) -> None:
    result = db.games.update_many(
        {"category": {"$exists": False}},
        {"$set": {"category": "fountain_pens"}},
    )
    print(f"[games] category backfilled: {result.modified_count}")

    result = db.games.update_many(
        {"schema_version": {"$exists": False}},
        {"$set": {"schema_version": 2}},
    )
    print(f"[games] schema_version set: {result.modified_count}")


def migrate_game_rounds(db) -> None:
    game_category = {g["_id"]: g.get("category", "fountain_pens") for g in db.games.find({}, {"category": 1})}

    updates = 0
    for row in db.game_rounds.find({}, {"game_id": 1, "category": 1}):
        update_set = {}
        if "category" not in row:
            gid = row.get("game_id")
            update_set["category"] = game_category.get(gid, "fountain_pens")
        if "schema_version" not in row:
            update_set["schema_version"] = 2
        if update_set:
            db.game_rounds.update_one({"_id": row["_id"]}, {"$set": update_set})
            updates += 1
    print(f"[game_rounds] migrated docs: {updates}")


def ensure_indexes(db) -> None:
    db.products.create_index([("category", 1), ("title", 1)])
    db.products.create_index([("category", 1), ("vendor", 1)])
    db.products.create_index([("category", 1), ("release_year", 1)])
    db.games.create_index([("category", 1), ("status", 1), ("created_at", -1)])
    db.games.create_index([("category", 1), ("player_name", 1), ("created_at", -1)])

    try:
        db.products.create_index([("category", 1), ("source_id", 1)], unique=True)
    except Exception as exc:  # noqa: BLE001
        print(f"[indexes] unable to create unique (category, source_id): {exc}")


def main() -> None:
    print(f"Using MongoDB: {settings.mongodb_url}")
    print(f"Database: {settings.mongodb_db_name}")
    backup_path = backup_database(settings.mongodb_db_name)
    print(f"Backup created at: {backup_path}")

    client = MongoClient(settings.mongodb_url)
    db = client[settings.mongodb_db_name]

    normalize_reference_types(db)
    migrate_products(db)
    migrate_games(db)
    migrate_game_rounds(db)
    ensure_indexes(db)

    missing_categories = db.products.count_documents({"category": {"$exists": False}})
    print(f"Post-check: products missing category = {missing_categories}")
    print("Migration complete.")
    client.close()


if __name__ == "__main__":
    main()
