from __future__ import annotations
"""Core game-service utilities and composition root."""

import hashlib
import random
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..category_profiles import category_copy, get_category_profile, normalize_category, supported_categories
from ..db import GameRecord, GameRoundRecord, ProductRecord, record_to_dict
from ..ml.prefix_cf import PrefixCFModel
from ..services.recommender import recommender
from .game_insights import GameInsightsMixin
from .game_play import GamePlayMixin


class GameService(GamePlayMixin, GameInsightsMixin):
    def __init__(self):
        self.recommender = recommender
        self._scoring_catalog_cache: dict[str, dict[str, Any]] = {}

    async def _ensure_indexes(self, db: AsyncSession) -> None:
        return None

    async def _ensure_model(self, db: AsyncSession) -> PrefixCFModel:
        if self.recommender.feature_space is None or self.recommender.model is None:
            await self.recommender.refresh(db)
        if self.recommender.feature_space is None or self.recommender.model is None:
            raise ValueError("Recommendation model is not initialized")
        return PrefixCFModel(self.recommender.feature_space)

    @staticmethod
    def _rng_for(game_id: str, round_number: int, salt: str) -> random.Random:
        seed_material = f"{game_id}:{round_number}:{salt}".encode("utf-8")
        seed = int(hashlib.sha256(seed_material).hexdigest()[:16], 16)
        return random.Random(seed)

    @staticmethod
    def _game_category(game: dict[str, Any]) -> str:
        try:
            return normalize_category(game.get("category"))
        except ValueError:
            return "fountain_pens"

    @staticmethod
    def _align_state_to_feature_space(model: PrefixCFModel, state: dict[str, Any]) -> bool:
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

    def _feature_projection(self, category: str) -> dict[str, int]:
        profile = get_category_profile(category)
        fields = {"category", *profile.categorical_fields, *profile.multi_fields, *profile.numeric_fields}
        return {field: 1 for field in fields}

    def _card_projection(self, category: str) -> dict[str, int]:
        projection = self._feature_projection(category)
        for field in ("title", "images"):
            projection[field] = 1
        return projection

    def _product_card(self, product: dict[str, Any], category: str | None = None) -> dict[str, Any]:
        resolved_category = normalize_category(category or product.get("category") or "fountain_pens")
        profile = get_category_profile(resolved_category)
        image_url = None
        images = product.get("images") or []
        if images:
            image_url = images[0].get("url")

        badges: list[str] = []
        subtitle = product.get("vendor")
        attributes: dict[str, Any] = {}
        for field in (*profile.categorical_fields, *profile.multi_fields, *profile.numeric_fields):
            if field in {"tags", "vendor"}:
                continue
            value = product.get(field)
            if value is not None:
                attributes[field] = value
        if resolved_category == "movies":
            release_year = product.get("release_year")
            runtime = product.get("runtime_minutes")
            vote_avg = product.get("vote_average")
            if release_year:
                badges.append(str(release_year))
            if runtime:
                badges.append(f"{runtime}m")
            if vote_avg:
                badges.append(f"{float(vote_avg):.1f}*")
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
            "attributes": attributes,
            "meta_badges": badges,
            "tags": product.get("tags", [])[:8],
            "image_url": image_url,
        }

    async def _get_game(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        row = await db.scalar(select(GameRecord).where(GameRecord.id == game_id))
        if row is None:
            raise ValueError("Game not found")
        game = record_to_dict(row)
        if "category" not in game:
            game["category"] = "fountain_pens"
        return game

    async def _get_products_by_ids(
        self,
        db: AsyncSession,
        ids: list[str],
        projection: dict[str, int] | None = None,
    ) -> list[dict[str, Any]]:
        if not ids:
            return []
        rows = (await db.execute(select(ProductRecord).where(ProductRecord.id.in_(ids)))).scalars().all()
        by_id = {row.id: record_to_dict(row) for row in rows}
        docs = [by_id[pid] for pid in ids if pid in by_id]
        if projection:
            projected: list[dict[str, Any]] = []
            include_keys = {k for k, v in projection.items() if v}
            for doc in docs:
                item = {}
                for key in include_keys:
                    if key in doc:
                        item[key] = doc[key]
                if projection.get("_id", 1):
                    item["_id"] = doc["_id"]
                projected.append(item)
            return projected
        return docs

    async def _completed_pick_ids(self, db: AsyncSession, game_id: str) -> list[str]:
        rows = (
            await db.execute(
                select(GameRoundRecord)
                .where(and_(GameRoundRecord.game_id == game_id, GameRoundRecord.completed.is_(True)))
                .order_by(GameRoundRecord.round_number.asc())
            )
        ).scalars().all()
        return [row.human_pick_id for row in rows if row.human_pick_id]

    async def _current_selection_sequence(
        self,
        db: AsyncSession,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        picked = await self._completed_pick_ids(db, str(game["_id"]))
        sequence = list(game.get("onboarding_selected_ids", [])) + picked
        if include_product_id:
            sequence.append(include_product_id)
        return sequence

    async def _metrics_for_state(
        self,
        db: AsyncSession,
        model: PrefixCFModel,
        state: dict[str, Any],
        selected_ids: list[str],
        category: str,
    ) -> dict[str, float]:
        products = await self._get_products_by_ids(
            db,
            selected_ids,
            projection=self._feature_projection(category),
        )
        vectors = [self.recommender.feature_space.vectorize(p) for p in products]
        coherence_score = model.coherence_score(vectors)
        predicted_prefix_rating = model.predict_prefix_rating(state)
        return {
            "coherence_score": float(coherence_score),
            "predicted_prefix_rating": float(predicted_prefix_rating),
        }

    async def _all_products_for_scoring(self, db: AsyncSession, category: str) -> list[dict[str, Any]]:
        current_count = await db.scalar(select(func.count()).select_from(ProductRecord).where(ProductRecord.category == category))
        cached = self._scoring_catalog_cache.get(category)
        if cached and cached.get("count") == int(current_count or 0):
            return cached["products"]
        rows = (await db.execute(select(ProductRecord).where(ProductRecord.category == category))).scalars().all()
        products = [record_to_dict(row) for row in rows]
        self._scoring_catalog_cache[category] = {
            "count": int(current_count or 0),
            "products": products,
            "loaded_at": datetime.utcnow(),
        }
        return products

    async def _all_products_for_onboarding_sample(self, db: AsyncSession, category: str) -> list[dict[str, Any]]:
        rows = (await db.execute(select(ProductRecord).where(ProductRecord.category == category))).scalars().all()
        return [record_to_dict(row) for row in rows]

    async def _warm_scoring_catalog(self, db: AsyncSession, category: str) -> None:
        try:
            await self._all_products_for_scoring(db, category)
        except Exception:
            return

    def _diverse_onboarding_sample(
        self,
        all_products: list[dict[str, Any]],
        game_id: str,
        category: str,
    ) -> list[str]:
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
            score = float(min(5.0, max(1.0, 3.0 + 1.7 * similarity + bias)))
            scored.append((score, product))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)
        return scored

    def _build_round_candidates(
        self,
        game_id: str,
        round_number: int,
        scored: list[tuple[float, dict[str, Any]]],
    ) -> list[str]:
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

    async def get_categories(self, db: AsyncSession) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(ProductRecord.category, func.count(ProductRecord.id))
                .group_by(ProductRecord.category)
            )
        ).all()
        counts = {str(category): int(count) for category, count in rows}
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
        db: AsyncSession,
        player_name: str,
        category: str = "fountain_pens",
        total_rounds: int = 5,
    ) -> dict[str, Any]:
        await self._ensure_indexes(db)
        model = await self._ensure_model(db)
        normalized_category = normalize_category(category)
        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name is required")
        now = datetime.utcnow()
        game = GameRecord(
            schema_version=2,
            player_name=clean_name,
            category=normalized_category,
            status="onboarding",
            current_round=0,
            total_rounds=total_rounds,
            human_score=0,
            ai_score=0,
            model_state=model.init_state(),
            onboarding_pool_ids=[],
            onboarding_selected_ids=[],
            onboarding_rating=None,
            created_at=now,
            updated_at=now,
        )
        db.add(game)
        await db.commit()
        await db.refresh(game)
        return {
            "id": game.id,
            "player_name": game.player_name,
            "category": normalized_category,
            "status": game.status,
            "total_rounds": game.total_rounds,
            "human_score": game.human_score,
            "ai_score": game.ai_score,
            "created_at": game.created_at,
        }


game_service = GameService()
