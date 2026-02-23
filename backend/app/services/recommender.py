from __future__ import annotations
"""Reusable recommendation engine wrapper over MongoDB collections.

This service owns:
- feature-space/model refresh from `products`
- item-vector caches used for scoring
- integration with the PBCF component (`PBCFEngine`)
"""

import random
from typing import Any

import numpy as np
from bson import ObjectId
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..ml.prefix_cf import FeatureSpace, PrefixCFModel
from ..ml.pbcf_nmf import PBCFEngine
from ..models import Product


class Recommender:
    """Mongo-backed recommendation service used by game and legacy endpoints."""

    def __init__(self):
        """Initialize in-memory model references and caches."""
        self.feature_space: FeatureSpace | None = None
        self.model: PrefixCFModel | None = None
        self.item_vectors: dict[str, np.ndarray] = {}
        self.item_norms: dict[str, float] = {}
        self.pbcf = PBCFEngine(k=6, iters=40)
        self._rating_count = 0

    async def refresh(self, db: AsyncIOMotorDatabase) -> None:
        """Rebuild feature space, model wrapper, and per-item vector caches."""
        products_cursor = db.products.find()
        products = [Product(**p) for p in await products_cursor.to_list(length=None)]

        self.feature_space = FeatureSpace.build(products)
        self.model = PrefixCFModel(self.feature_space)
        self.item_vectors = {str(p.id): self.feature_space.vectorize(p) for p in products}
        self.item_norms = {pid: float(np.linalg.norm(vec)) for pid, vec in self.item_vectors.items()}
        await self._refresh_pbcf(db)

    async def _refresh_pbcf(self, db: AsyncIOMotorDatabase) -> None:
        """Retrain PBCF only when prefix-rating count has changed."""
        count = await db.prefix_ratings.count_documents({})
        if count != self._rating_count:
            self._rating_count = count
            await self.pbcf.train(db)

    def load_state(self, game: dict[str, Any]) -> dict:
        """Read model state from game doc or create an empty initial state."""
        state = game.get("model_state", {})
        if not state:
            assert self.model is not None
            state = self.model.init_state()
        return state

    async def save_state(self, db: AsyncIOMotorDatabase, game_id: str, state: dict) -> None:
        """Persist updated model state into the game document."""
        gid: str | ObjectId = game_id
        if ObjectId.is_valid(game_id):
            gid = ObjectId(game_id)
        await db.games.update_one(
            {"_id": gid},
            {"$set": {"model_state": state}}
        )

    async def update_with_selection(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
        game: dict[str, Any],
        product: Product,
        is_exception: bool
    ) -> None:
        """Apply a product selection update and persist resulting state."""
        assert self.model is not None
        state = self.load_state(game)
        self.model.update_with_selection(state, product, is_exception)
        await self.save_state(db, game_id, state)

    async def update_with_prefix_rating(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
        game: dict[str, Any],
        rating: int
    ) -> None:
        """Apply onboarding/prefix rating update and persist resulting state."""
        assert self.model is not None
        state = self.load_state(game)
        self.model.update_with_prefix_rating(state, rating)
        await self.save_state(db, game_id, state)

    async def recommend(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
        game: dict[str, Any],
        limit: int = 2
    ) -> dict:
        """Generate strong picks + wildcard with coherence/prefix metrics."""
        assert self.model is not None
        if not self.item_vectors:
            await self.refresh(db)
        await self._refresh_pbcf(db)

        state = self.load_state(game)

        # Get selected products from game (onboarding selections + completed rounds picks)
        selected_product_ids: set[str] = set()
        selected_product_ids.update(game.get("onboarding_selected_ids", []))
        
        # Get completed round picks if any
        gid = ObjectId(game_id) if ObjectId.is_valid(game_id) else game_id
        rounds = await db.game_rounds.find(
            {"game_id": gid, "completed": True},
            {"human_pick_id": 1},
        ).to_list(length=None)
        selected_product_ids.update({str(r.get("human_pick_id")) for r in rounds if r.get("human_pick_id")})

        # Get candidate products (not already selected)
        excluded_object_ids = [ObjectId(pid) for pid in selected_product_ids if ObjectId.is_valid(pid)]
        products_cursor = db.products.find({"_id": {"$nin": excluded_object_ids}})
        candidates = [Product(**p) for p in await products_cursor.to_list(length=None)]

        # Get predicted ratings from PBCF
        user_id = str(game.get("_id", ""))
        predicted_ratings = await self.pbcf.predict_user_ratings(db, user_id)

        # Build current prefix
        current_prefix = "-".join(sorted(selected_product_ids)) if selected_product_ids else ""

        # Score candidates
        scored = []
        for product in candidates:
            vec = self.item_vectors.get(str(product.id))
            if vec is None:
                continue

            # Use PBCF prediction if available, otherwise fall back to content-based
            prefix_key = f"{current_prefix}-{product.id}" if current_prefix else str(product.id)
            if prefix_key in predicted_ratings:
                score = predicted_ratings[prefix_key]
            else:
                score = self.model.score_item(state, vec)

            scored.append((score, product, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        strong = scored[:limit]

        # Select wildcard from diverse pool
        wildcard = None
        if scored:
            diverse_pool = scored[-max(10, len(scored) // 8):]
            wildcard = random.choice(diverse_pool)[1]

        # Calculate metrics
        selected_vecs = [
            self.item_vectors[sid]
            for sid in selected_product_ids
            if sid in self.item_vectors
        ]
        coherence = self.model.coherence_score(selected_vecs)
        predicted_prefix = self.model.predict_prefix_rating(state)

        return {
            "strong": [p for _, p, _ in strong],
            "wildcard": wildcard,
            "coherence_score": coherence,
            "predicted_prefix_rating": predicted_prefix,
        }

    async def get_pbcf_stats(self, db: AsyncIOMotorDatabase) -> dict:
        """Return lightweight PBCF training/status statistics."""
        await self._refresh_pbcf(db)
        return self.pbcf.get_stats()


# Global recommender instance
recommender = Recommender()
