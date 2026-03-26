"""Recommendation engine facade for model refresh, state updates, and inference."""

from __future__ import annotations

import random
from typing import Any

import numpy as np
from sqlalchemy import and_, func, not_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import (
    GameRecord,
    GameRoundRecord,
    PrefixRatingRecord,
    ProductRecord,
    record_to_dict,
)
from ..ml.pbcf_nmf import PBCFEngine
from ..ml.prefix_cf import FeatureSpace, PrefixCFModel
from ..models import Product


class Recommender:
    """Coordinates feature/model state and PBCF signals over persisted game data."""

    def __init__(self):
        """Initialize model handles and in-memory vector caches."""
        self.feature_space: FeatureSpace | None = None
        self.model: PrefixCFModel | None = None
        self.item_vectors: dict[str, np.ndarray] = {}
        self.item_norms: dict[str, float] = {}
        self.pbcf = PBCFEngine(k=6, iters=40)
        self._rating_count = 0
        self._product_count = 0

    async def refresh(self, db: AsyncSession) -> None:
        """Rebuild feature space/model and cached item vectors from current products."""
        rows = (await db.execute(select(ProductRecord))).scalars().all()
        products = [Product(**record_to_dict(row)) for row in rows]
        self._product_count = len(products)
        self.feature_space = FeatureSpace.build(products)
        self.model = PrefixCFModel(self.feature_space)
        self.item_vectors = {str(p.id): self.feature_space.vectorize(p) for p in products}
        self.item_norms = {pid: float(np.linalg.norm(vec)) for pid, vec in self.item_vectors.items()}
        await self._refresh_pbcf(db)

    async def ensure_fresh(self, db: AsyncSession) -> None:
        """Refresh model caches when product catalog shape changes."""
        current_count = int((await db.scalar(select(func.count()).select_from(ProductRecord))) or 0)
        if self.feature_space is None or self.model is None or current_count != self._product_count:
            await self.refresh(db)

    async def _refresh_pbcf(self, db: AsyncSession) -> None:
        """Retrain PBCF only when rating count has changed."""
        count = await db.scalar(select(func.count()).select_from(PrefixRatingRecord))
        if count != self._rating_count:
            self._rating_count = int(count or 0)
            await self.pbcf.train(db)

    def load_state(self, game: dict[str, Any]) -> dict:
        """Load game model state or initialize default state."""
        state = game.get("model_state", {})
        if not state:
            assert self.model is not None
            state = self.model.init_state()
        return state

    async def save_state(self, db: AsyncSession, game_id: str, state: dict) -> None:
        """Persist model state for a game record."""
        game = await db.scalar(select(GameRecord).where(GameRecord.id == game_id))
        if game:
            game.model_state = state
            await db.commit()

    async def update_with_selection(
        self,
        db: AsyncSession,
        game_id: str,
        game: dict[str, Any],
        product: Product,
        is_exception: bool,
    ) -> None:
        """Apply a product-selection update to a game's model state."""
        assert self.model is not None
        state = self.load_state(game)
        self.model.update_with_selection(state, product, is_exception)
        await self.save_state(db, game_id, state)

    async def update_with_prefix_rating(
        self,
        db: AsyncSession,
        game_id: str,
        game: dict[str, Any],
        rating: int,
    ) -> None:
        """Apply onboarding prefix-rating feedback to a game's model state."""
        assert self.model is not None
        state = self.load_state(game)
        self.model.update_with_prefix_rating(state, rating)
        await self.save_state(db, game_id, state)

    async def recommend(
        self,
        db: AsyncSession,
        game_id: str,
        game: dict[str, Any],
        limit: int = 2,
    ) -> dict:
        """Return strong and wildcard recommendations plus diagnostic metrics."""
        assert self.model is not None
        if not self.item_vectors:
            await self.refresh(db)
        await self._refresh_pbcf(db)

        state = self.load_state(game)
        selected_product_ids: set[str] = set(game.get("onboarding_selected_ids", []))

        rounds = (
            (
                await db.execute(
                    select(GameRoundRecord).where(
                        and_(GameRoundRecord.game_id == game_id, GameRoundRecord.completed.is_(True))
                    )
                )
            )
            .scalars()
            .all()
        )
        selected_product_ids.update({str(r.human_pick_id) for r in rounds if r.human_pick_id})

        if selected_product_ids:
            stmt = select(ProductRecord).where(not_(ProductRecord.id.in_(list(selected_product_ids))))
        else:
            stmt = select(ProductRecord)
        candidates = [Product(**record_to_dict(row)) for row in (await db.execute(stmt)).scalars().all()]

        user_id = str(game.get("_id", ""))
        predicted_ratings = await self.pbcf.predict_user_ratings(db, user_id)
        current_prefix = "-".join(sorted(selected_product_ids)) if selected_product_ids else ""

        scored = []
        for product in candidates:
            vec = self.item_vectors.get(str(product.id))
            if vec is None:
                continue
            prefix_key = f"{current_prefix}-{product.id}" if current_prefix else str(product.id)
            score = predicted_ratings.get(prefix_key, self.model.score_item(state, vec))
            scored.append((score, product, vec))

        scored.sort(key=lambda x: x[0], reverse=True)
        strong = scored[:limit]
        wildcard = random.choice(scored[-max(10, len(scored) // 8) :])[1] if scored else None

        selected_vecs = [self.item_vectors[sid] for sid in selected_product_ids if sid in self.item_vectors]
        coherence = self.model.coherence_score(selected_vecs)
        predicted_prefix = self.model.predict_prefix_rating(state)

        return {
            "strong": [p for _, p, _ in strong],
            "wildcard": wildcard,
            "coherence_score": coherence,
            "predicted_prefix_rating": predicted_prefix,
        }

    async def get_pbcf_stats(self, db: AsyncSession) -> dict:
        """Return current PBCF training/statistics snapshot."""
        await self._refresh_pbcf(db)
        return self.pbcf.get_stats()


recommender = Recommender()
