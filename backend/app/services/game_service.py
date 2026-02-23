from __future__ import annotations
"""Core game-service utilities and composition root.

`GameService` contains shared helper methods used across gameplay and insights.
High-level endpoints are implemented in mixins:
- `GamePlayMixin` (onboarding, rounds, picks)
- `GameInsightsMixin` (summary, status, leaderboard, history)
"""

import hashlib
import random
from datetime import datetime
from typing import Any

import numpy as np
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..category_profiles import (
    category_copy,
    get_category_profile,
    normalize_category,
    supported_categories,
)
from ..ml.prefix_cf import PrefixCFModel
from ..services.recommender import recommender
from .game_insights import GameInsightsMixin
from .game_play import GamePlayMixin


class GameService(GamePlayMixin, GameInsightsMixin):
    """Sequential preference game service (50->10 onboarding, 5-round duel)."""

    def __init__(self):
        """Initialize shared dependencies and in-memory caches."""
        self.recommender = recommender
        self._indexes_ready = False
        self._scoring_catalog_cache: dict[str, dict[str, Any]] = {}

    async def _ensure_indexes(self, db: AsyncIOMotorDatabase) -> None:
        """Create MongoDB indexes once per process for game-critical collections."""
        if self._indexes_ready:
            return

        await db.games.create_index([("status", 1), ("created_at", -1)])
        await db.games.create_index([("player_name", 1), ("created_at", -1)])
        await db.games.create_index([("category", 1), ("status", 1), ("created_at", -1)])
        await db.games.create_index([("category", 1), ("player_name", 1), ("created_at", -1)])
        await db.game_rounds.create_index(
            [("game_id", 1), ("round_number", 1)],
            unique=True,
            name="game_id_round_number_unique_v2",
            partialFilterExpression={"game_id": {"$type": "objectId"}},
        )
        await db.game_rounds.create_index([("game_id", 1), ("created_at", -1)])
        await db.products.create_index([("category", 1), ("source_id", 1)], unique=True)
        await db.products.create_index([("category", 1), ("title", 1)])
        await db.products.create_index([("category", 1), ("vendor", 1)])
        await db.products.create_index([("category", 1), ("release_year", 1)])
        self._indexes_ready = True

    async def _ensure_model(self, db: AsyncIOMotorDatabase) -> PrefixCFModel:
        """Ensure feature space/model are loaded and return a fresh model wrapper."""
        if self.recommender.feature_space is None or self.recommender.model is None:
            await self.recommender.refresh(db)

        if self.recommender.feature_space is None or self.recommender.model is None:
            raise ValueError("Recommendation model is not initialized")

        return PrefixCFModel(self.recommender.feature_space)

    @staticmethod
    def _rng_for(game_id: str, round_number: int, salt: str) -> random.Random:
        """Build deterministic RNG for reproducible sampling per game/round."""
        seed_material = f"{game_id}:{round_number}:{salt}".encode("utf-8")
        seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16)
        return random.Random(seed)

    @staticmethod
    def _to_object_id(value: str, label: str) -> ObjectId:
        """Validate and convert a string to Mongo ObjectId."""
        if not ObjectId.is_valid(value):
            raise ValueError(f"Invalid {label}")
        return ObjectId(value)

    @staticmethod
    def _game_category(game: dict[str, Any]) -> str:
        """Return normalized game category, defaulting to fountain pens."""
        try:
            return normalize_category(game.get("category"))
        except ValueError:
            return "fountain_pens"

    @staticmethod
    def _align_state_to_feature_space(model: PrefixCFModel, state: dict[str, Any]) -> bool:
        """Pad/truncate persisted user vectors when feature space evolves over time."""
        expected_dim = len(model.feature_space.feature_index)
        raw_vec = state.get("user_vec")
        changed = False

        if not isinstance(raw_vec, list):
            vec = [0.0] * expected_dim
            changed = True
        else:
            vec: list[float] = []
            for value in raw_vec:
                try:
                    vec.append(float(value))
                except (TypeError, ValueError):
                    vec.append(0.0)
                    changed = True

            if len(vec) < expected_dim:
                vec.extend([0.0] * (expected_dim - len(vec)))
                changed = True
            elif len(vec) > expected_dim:
                vec = vec[:expected_dim]
                changed = True

        state["user_vec"] = vec
        return changed

    @staticmethod
    def _category_product_filter(category: str) -> dict[str, Any]:
        """Build product query filter while preserving legacy uncategorized pen docs."""
        if category == "fountain_pens":
            return {"$or": [{"category": "fountain_pens"}, {"category": {"$exists": False}}]}
        return {"category": category}

    @staticmethod
    def _category_query(category: str) -> dict[str, Any]:
        """Build game/leaderboard query filter with the same category compatibility rule."""
        if category == "fountain_pens":
            return {"$or": [{"category": "fountain_pens"}, {"category": {"$exists": False}}]}
        return {"category": category}

    def _product_card(self, product: dict[str, Any], category: str | None = None) -> dict[str, Any]:
        """Convert a raw product doc into the frontend-facing product card payload."""
        resolved_category = normalize_category(category or product.get("category") or "fountain_pens")
        profile = get_category_profile(resolved_category)
        image_url = None
        images = product.get("images") or []
        if images:
            image_url = images[0].get("url")

        badges: list[str] = []
        subtitle = product.get("vendor")
        if resolved_category == "movies":
            release_year = product.get("release_year")
            runtime = product.get("runtime_minutes")
            vote_avg = product.get("vote_average")
            if release_year:
                badges.append(str(release_year))
            if runtime:
                badges.append(f"{runtime}m")
            if vote_avg:
                badges.append(f"{float(vote_avg):.1f}★")
            directors = product.get("directors") or []
            if directors:
                subtitle = f"Dir. {directors[0]}"
            elif product.get("vendor"):
                subtitle = f"{profile.vendor_label}: {product.get('vendor')}"

        return {
            "id": str(product["_id"]),
            "category": resolved_category,
            "title": product.get("title") or "Untitled",
            "vendor": product.get("vendor"),
            "subtitle": subtitle,
            "price_min": product.get("price_min"),
            "price_max": product.get("price_max"),
            "release_year": product.get("release_year"),
            "runtime_minutes": product.get("runtime_minutes"),
            "vote_average": product.get("vote_average"),
            "meta_badges": badges,
            "tags": product.get("tags", [])[:8],
            "image_url": image_url,
        }

    async def _get_game(self, db: AsyncIOMotorDatabase, game_id: str) -> dict[str, Any]:
        """Fetch and validate a game document by ID."""
        oid = self._to_object_id(game_id, "game ID")
        game = await db.games.find_one({"_id": oid})
        if game is None:
            raise ValueError("Game not found")
        if "category" not in game:
            game["category"] = "fountain_pens"
        return game

    async def _get_products_by_ids(
        self,
        db: AsyncIOMotorDatabase,
        ids: list[str],
        projection: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        """Load products by ID and preserve input order in the returned list."""
        object_ids = [ObjectId(pid) for pid in ids if ObjectId.is_valid(pid)]
        if not object_ids:
            return []
        cursor = db.products.find({"_id": {"$in": object_ids}}, projection)
        products = await cursor.to_list(length=len(object_ids))
        by_id = {str(p["_id"]): p for p in products}
        return [by_id[pid] for pid in ids if pid in by_id]

    async def _completed_pick_ids(self, db: AsyncIOMotorDatabase, game_id: str) -> list[str]:
        """Return ordered human picks from completed rounds."""
        oid = self._to_object_id(game_id, "game ID")
        cursor = db.game_rounds.find(
            {"game_id": oid, "completed": True},
            {"human_pick_id": 1, "_id": 0},
        ).sort("round_number", 1)
        rounds = await cursor.to_list(length=None)
        return [row["human_pick_id"] for row in rounds if row.get("human_pick_id")]

    async def _current_selection_sequence(
        self,
        db: AsyncIOMotorDatabase,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        """Build full sequence: onboarding picks + completed round picks (+ optional current pick)."""
        picked = await self._completed_pick_ids(db, str(game["_id"]))
        sequence = list(game.get("onboarding_selected_ids", [])) + picked
        if include_product_id:
            sequence.append(include_product_id)
        return sequence

    async def _metrics_for_state(
        self,
        db: AsyncIOMotorDatabase,
        model: PrefixCFModel,
        state: dict[str, Any],
        selected_ids: list[str],
    ) -> dict[str, float]:
        """Compute coherence and predicted prefix rating for the current state."""
        products = await self._get_products_by_ids(
            db,
            selected_ids,
            projection={
                "category": 1,
                "vendor": 1,
                "product_type": 1,
                "tags": 1,
                "options": 1,
                "price_min": 1,
                "price_max": 1,
                "release_year": 1,
                "runtime_minutes": 1,
                "vote_average": 1,
                "popularity": 1,
                "original_language": 1,
                "certification": 1,
                "primary_country": 1,
                "decade_bucket": 1,
                "runtime_bucket": 1,
                "genres": 1,
                "keywords": 1,
                "production_companies": 1,
                "directors": 1,
            },
        )
        vectors = [self.recommender.feature_space.vectorize(p) for p in products]
        coherence_score = model.coherence_score(vectors)
        predicted_prefix_rating = model.predict_prefix_rating(state)
        return {
            "coherence_score": float(coherence_score),
            "predicted_prefix_rating": float(predicted_prefix_rating),
        }

    async def _all_products_for_scoring(
        self,
        db: AsyncIOMotorDatabase,
        category: str,
    ) -> list[dict[str, Any]]:
        """Return full scoring catalog for a category with count-based cache invalidation."""
        query = self._category_product_filter(category)
        current_count = await db.products.count_documents(query)
        cached = self._scoring_catalog_cache.get(category)
        if cached and cached.get("count") == current_count:
            return cached["products"]

        # Keep this projection minimal because this query runs for candidate ranking.
        cursor = db.products.find(
            query,
            {
                "category": 1,
                "title": 1,
                "vendor": 1,
                "price_min": 1,
                "price_max": 1,
                "tags": 1,
                "product_type": 1,
                "options": 1,
                "release_year": 1,
                "runtime_minutes": 1,
                "vote_average": 1,
                "popularity": 1,
                "original_language": 1,
                "certification": 1,
                "primary_country": 1,
                "decade_bucket": 1,
                "runtime_bucket": 1,
                "genres": 1,
                "keywords": 1,
                "production_companies": 1,
                "directors": 1,
            },
        )
        products = await cursor.to_list(length=None)
        self._scoring_catalog_cache[category] = {
            "count": current_count,
            "products": products,
            "loaded_at": datetime.utcnow(),
        }
        return products

    async def _all_products_for_onboarding_sample(
        self,
        db: AsyncIOMotorDatabase,
        category: str,
    ) -> list[dict[str, Any]]:
        """Load minimal fields required to build a diverse onboarding pool."""
        cursor = db.products.find(
            self._category_product_filter(category),
            {
                "vendor": 1,
                "price_min": 1,
                "popularity": 1,
                "release_year": 1,
            },
        )
        return await cursor.to_list(length=None)

    async def _warm_scoring_catalog(self, db: AsyncIOMotorDatabase, category: str) -> None:
        """Best-effort background warmup for catalog cache used in round generation."""
        try:
            await self._all_products_for_scoring(db, category)
        except Exception:
            # Best effort only; requests can continue without warm cache.
            return

    def _diverse_onboarding_sample(
        self,
        all_products: list[dict[str, Any]],
        game_id: str,
        category: str,
    ) -> list[str]:
        """Sample 50 onboarding items with vendor and numeric-bucket diversity."""
        if len(all_products) <= 50:
            return [str(p["_id"]) for p in all_products]

        rng = self._rng_for(game_id, 0, "onboarding")
        products = list(all_products)
        rng.shuffle(products)

        numeric_field = "price_min" if category == "fountain_pens" else "popularity"
        values = [float(p.get(numeric_field) or 0.0) for p in products]
        if max(values, default=0.0) == 0.0 and category == "movies":
            numeric_field = "release_year"
            values = [float(p.get(numeric_field) or 0.0) for p in products]
        sorted_values = sorted(values)
        q1 = sorted_values[len(sorted_values) // 3]
        q2 = sorted_values[(2 * len(sorted_values)) // 3]

        low: list[dict[str, Any]] = []
        mid: list[dict[str, Any]] = []
        high: list[dict[str, Any]] = []
        for p in products:
            value = float(p.get(numeric_field) or 0.0)
            if value <= q1:
                low.append(p)
            elif value <= q2:
                mid.append(p)
            else:
                high.append(p)

        def round_robin_pick(bucket: list[dict[str, Any]], target: int) -> list[dict[str, Any]]:
            by_vendor: dict[str, list[dict[str, Any]]] = {}
            for item in bucket:
                vendor = item.get("vendor") or "Unknown"
                by_vendor.setdefault(vendor, []).append(item)
            for vendor_items in by_vendor.values():
                rng.shuffle(vendor_items)
            vendor_keys = list(by_vendor.keys())
            rng.shuffle(vendor_keys)

            picks: list[dict[str, Any]] = []
            while len(picks) < target and vendor_keys:
                next_vendor_keys: list[str] = []
                for vendor in vendor_keys:
                    items = by_vendor[vendor]
                    if items:
                        picks.append(items.pop())
                        if len(picks) >= target:
                            break
                    if items:
                        next_vendor_keys.append(vendor)
                vendor_keys = next_vendor_keys
            return picks

        chosen = round_robin_pick(low, 17) + round_robin_pick(mid, 17) + round_robin_pick(high, 16)
        chosen_ids = {str(p["_id"]) for p in chosen}

        if len(chosen) < 50:
            remainder = [p for p in products if str(p["_id"]) not in chosen_ids]
            rng.shuffle(remainder)
            chosen.extend(remainder[: 50 - len(chosen)])

        chosen = chosen[:50]
        rng.shuffle(chosen)
        return [str(p["_id"]) for p in chosen]

    def _rank_candidates(
        self,
        model: PrefixCFModel,
        state: dict[str, Any],
        products: list[dict[str, Any]],
    ) -> list[tuple[float, dict[str, Any]]]:
        """Score candidate products against the current user state."""
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        feature_dim = len(model.feature_space.feature_index)
        if user_vec.size < feature_dim:
            user_vec = np.pad(user_vec, (0, feature_dim - user_vec.size))
        elif user_vec.size > feature_dim:
            user_vec = user_vec[:feature_dim]
        user_norm = float(np.linalg.norm(user_vec))
        bias = float(state.get("bias", 0.0))
        item_vectors = self.recommender.item_vectors
        item_norms = self.recommender.item_norms

        scored: list[tuple[float, dict[str, Any]]] = []
        for product in products:
            pid = str(product["_id"])
            vec = item_vectors.get(pid)
            if vec is None:
                vec = self.recommender.feature_space.vectorize(product)
                item_vectors[pid] = vec
                item_norms[pid] = float(np.linalg.norm(vec))

            if user_norm <= 0:
                similarity = 0.0
            else:
                item_norm = item_norms.get(pid)
                if item_norm is None:
                    item_norm = float(np.linalg.norm(vec))
                    item_norms[pid] = item_norm
                denom = user_norm * item_norm
                similarity = float(np.dot(user_vec, vec) / denom) if denom > 0 else 0.0

            score = 3.0 + 1.7 * similarity + bias
            score = float(min(5.0, max(1.0, score)))
            scored.append((float(score), product))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)
        return scored

    def _build_round_candidates(
        self,
        game_id: str,
        round_number: int,
        scored: list[tuple[float, dict[str, Any]]],
    ) -> list[str]:
        """Choose 10 round candidates from scored items using quality/diversity buckets."""
        rng = self._rng_for(game_id, round_number, "round_candidates")
        if len(scored) <= 10:
            ids = [str(p["_id"]) for _, p in scored]
            rng.shuffle(ids)
            return ids

        selected_ids: list[str] = []
        selected_set: set[str] = set()

        def add_from_pool(pool: list[tuple[float, dict[str, Any]]], target: int) -> None:
            pool_items = list(pool)
            rng.shuffle(pool_items)
            for _, product in pool_items:
                pid = str(product["_id"])
                if pid in selected_set:
                    continue
                selected_set.add(pid)
                selected_ids.append(pid)
                if len(selected_ids) >= target:
                    return

        likely = scored[:20]
        add_from_pool(likely, 6)

        near_boundary = scored[20:120] or scored[6:120]
        add_from_pool(near_boundary, 8)

        likely_vendors = {p.get("vendor") for _, p in scored[:10]}
        tail = scored[len(scored) // 2 :]
        diverse = [pair for pair in tail if pair[1].get("vendor") not in likely_vendors]
        if len(diverse) < 2:
            diverse = tail
        add_from_pool(diverse, 10)

        add_from_pool(scored, 10)

        selected_ids = selected_ids[:10]
        rng.shuffle(selected_ids)
        return selected_ids

    async def get_categories(self, db: AsyncIOMotorDatabase) -> list[dict[str, Any]]:
        """Return supported categories with display copy and available item counts."""
        pipeline = [
            {
                "$group": {
                    "_id": {"$ifNull": ["$category", "fountain_pens"]},
                    "available_count": {"$sum": 1},
                }
            }
        ]
        counts = {row["_id"]: int(row["available_count"]) for row in await db.products.aggregate(pipeline).to_list(length=None)}

        results: list[dict[str, Any]] = []
        for category in supported_categories():
            copy = category_copy(category)
            results.append(
                {
                    "id": category,
                    "display_name": copy["display_name"],
                    "item_singular": copy["item_singular"],
                    "item_plural": copy["item_plural"],
                    "available_count": counts.get(category, 0),
                }
            )
        return results

    async def create_game(
        self,
        db: AsyncIOMotorDatabase,
        player_name: str,
        category: str = "fountain_pens",
        total_rounds: int = 5,
    ) -> dict[str, Any]:
        """Create a new game document and initialize model state."""
        await self._ensure_indexes(db)
        model = await self._ensure_model(db)
        normalized_category = normalize_category(category)

        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name is required")

        now = datetime.utcnow()
        game_doc = {
            "schema_version": 2,
            "player_name": clean_name,
            "category": normalized_category,
            "status": "onboarding",
            "current_round": 0,
            "total_rounds": total_rounds,
            "human_score": 0,
            "ai_score": 0,
            "model_state": model.init_state(),
            "onboarding_pool_ids": [],
            "onboarding_selected_ids": [],
            "onboarding_rating": None,
            "created_at": now,
            "updated_at": now,
        }

        result = await db.games.insert_one(game_doc)
        game = await db.games.find_one({"_id": result.inserted_id})
        assert game is not None

        return {
            "id": str(game["_id"]),
            "player_name": game["player_name"],
            "category": normalized_category,
            "status": game["status"],
            "total_rounds": game["total_rounds"],
            "human_score": game["human_score"],
            "ai_score": game["ai_score"],
            "created_at": game["created_at"],
        }


game_service = GameService()
