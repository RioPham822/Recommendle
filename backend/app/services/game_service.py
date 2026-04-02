"""Core game-service composition root and shared utility methods."""

from __future__ import annotations

import hashlib
import random
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..category_profiles import (
    category_display_schema,
    category_copy,
    clean_display_tags,
    get_category_profile,
    normalize_category,
    numeric_preference_label,
    humanize_feature as profile_humanize_feature,
    supported_categories,
    extract_feature_tokens,
)
from ..db import (
    GameRecord,
    GameRoundRecord,
    PrefixRatingRecord,
    ProductRecord,
    record_to_dict,
)
from ..ml.prefix_cf import PrefixCFModel
from ..services.recommender import recommender
from .game_insights import GameInsightsMixin
from .game_play import GamePlayMixin


class GameService(GamePlayMixin, GameInsightsMixin):
    """Primary game service combining gameplay and insights mixins."""

    REDESIGN_SCHEMA_VERSION = 3
    LEGACY_SCHEMA_VERSION = 2
    DEFAULT_MATCH_STREAK_TARGET = 5
    MIN_MOVIE_VOTE_COUNT = 1000

    def __init__(self):
        """Initialize shared recommender and in-memory scoring cache."""
        self.recommender = recommender
        self._scoring_catalog_cache: dict[str, dict[str, Any]] = {}

    async def _ensure_indexes(self, db: AsyncSession) -> None:
        """Compatibility shim for previous backends; indexes are managed in init_db."""
        return None

    async def _ensure_model(self, db: AsyncSession) -> PrefixCFModel:
        """Ensure feature space/model are loaded before scoring operations."""
        await self.recommender.ensure_fresh(db)
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
    def _normalize_mode(mode: str | None) -> str:
        if mode is None:
            return "classic"
        normalized = str(mode).strip().lower()
        if normalized in {"classic", "beta"}:
            return normalized
        raise ValueError(f"Unsupported game mode '{mode}'")

    @classmethod
    def _filter_visible_products(cls, products: list[dict[str, Any]], category: str) -> list[dict[str, Any]]:
        if category != "movies":
            return products
        visible: list[dict[str, Any]] = []
        for product in products:
            try:
                vote_count = int(product.get("vote_count") or 0)
            except (TypeError, ValueError):
                vote_count = 0
            if vote_count >= cls.MIN_MOVIE_VOTE_COUNT:
                visible.append(product)
        return visible

    @classmethod
    def _is_redesigned_game(cls, game: dict[str, Any] | None) -> bool:
        if not game:
            return False
        return int(game.get("schema_version") or cls.LEGACY_SCHEMA_VERSION) >= cls.REDESIGN_SCHEMA_VERSION

    @classmethod
    def _empty_seed_preferences(cls) -> dict[str, Any]:
        return {
            "likes": {},
            "dislikes": {},
            "like_product_ids": [],
            "dislike_product_ids": [],
        }

    @classmethod
    def _ensure_redesign_state(cls, state: dict[str, Any] | None) -> dict[str, Any]:
        normalized = dict(state or {})
        normalized.setdefault("match_streak_target", cls.DEFAULT_MATCH_STREAK_TARGET)
        normalized.setdefault("current_match_streak", 0)
        normalized.setdefault("longest_match_streak", 0)
        normalized.setdefault("rounds_played", 0)
        normalized.setdefault("total_matches", 0)
        normalized.setdefault("active_preference_ids", [])
        normalized.setdefault("seed_preferences", cls._empty_seed_preferences())
        return normalized

    @classmethod
    def _rounds_played(cls, game: dict[str, Any]) -> int:
        state = cls._ensure_redesign_state(game.get("model_state") or {})
        if cls._is_redesigned_game(game):
            return int(state.get("rounds_played") or game.get("current_round") or 0)
        return int(game.get("current_round") or 0)

    @classmethod
    def _match_progress(cls, game: dict[str, Any]) -> tuple[int, int, int]:
        state = cls._ensure_redesign_state(game.get("model_state") or {})
        return (
            int(state.get("current_match_streak") or 0),
            int(state.get("longest_match_streak") or 0),
            int(state.get("match_streak_target") or cls.DEFAULT_MATCH_STREAK_TARGET),
        )

    @classmethod
    def _reset_run_progress(cls, state: dict[str, Any] | None) -> dict[str, Any]:
        """Preserve learned preferences while resetting per-run counters."""
        reset = cls._ensure_redesign_state(state)
        reset["current_match_streak"] = 0
        reset["longest_match_streak"] = 0
        reset["rounds_played"] = 0
        reset["total_matches"] = 0
        return reset

    @staticmethod
    def _has_carryable_profile(game: GameRecord | dict[str, Any] | None) -> bool:
        """Return whether a completed session can seed a new run."""
        if not game:
            return False
        state = game.model_state if isinstance(game, GameRecord) else game.get("model_state")
        onboarding_selected_ids = (
            game.onboarding_selected_ids if isinstance(game, GameRecord) else game.get("onboarding_selected_ids")
        ) or []
        return isinstance(state, dict) and 1 <= len(onboarding_selected_ids) <= GamePlayMixin.MAX_ONBOARDING_SELECTIONS

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
        """Build field projection for model features of a category."""
        profile = get_category_profile(category)
        fields = {"category", *profile.categorical_fields, *profile.multi_fields, *profile.numeric_fields}
        return {field: 1 for field in fields}

    def _round_candidate_target(self, category: str) -> int:
        """Return number of candidates shown each round for this category."""
        profile = get_category_profile(category)
        return 2 if profile.round_mode == "duel" else 10

    def _card_projection(self, category: str) -> dict[str, int]:
        """Build projection for card rendering (features + title/image)."""
        projection = self._feature_projection(category)
        for field in ("title", "images", "vendor", "tags"):
            projection[field] = 1
        return projection

    def _product_card(self, product: dict[str, Any], category: str | None = None) -> dict[str, Any]:
        """Normalize a product into a category-aware UI card payload."""
        resolved_category = normalize_category(category or product.get("category") or "fountain_pens")
        profile = get_category_profile(resolved_category)

        def has_display_value(value: Any) -> bool:
            if value is None:
                return False
            if isinstance(value, str):
                return bool(value.strip())
            if isinstance(value, (list, tuple, set, dict)):
                return len(value) > 0
            return True

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
            if field == "options" and isinstance(value, dict):
                for option_name, option_values in value.items():
                    if has_display_value(option_values):
                        attributes[str(option_name)] = option_values
                continue
            if has_display_value(value):
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
            "tags": clean_display_tags(resolved_category, product.get("tags"), limit=8),
            "image_url": image_url,
            "description": product.get("description"),
            "url": product.get("url"),
        }

    async def _get_game(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        """Load one game row and normalize to dict shape used by services."""
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
        """Fetch products preserving requested ID order with optional projection."""
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
        """Return all completed human picks for a game in round order."""
        rows = (
            (
                await db.execute(
                    select(GameRoundRecord)
                    .where(and_(GameRoundRecord.game_id == game_id, GameRoundRecord.completed.is_(True)))
                    .order_by(GameRoundRecord.round_number.asc())
                )
            )
            .scalars()
            .all()
        )
        return [row.human_pick_id for row in rows if row.human_pick_id]

    async def _historical_selection_sequence(
        self,
        db: AsyncSession,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        """Return all onboarding and round picks in encounter order."""
        picked = await self._completed_pick_ids(db, str(game["_id"]))
        sequence = list(game.get("onboarding_selected_ids", [])) + picked
        if include_product_id:
            sequence.append(include_product_id)
        return sequence

    async def _active_preference_sequence(
        self,
        db: AsyncSession,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        """Return the current preference deck, falling back to historical picks."""
        state = self._ensure_redesign_state(game.get("model_state") or {})
        active = [str(pid) for pid in state.get("active_preference_ids") or [] if pid]
        if active:
            sequence = list(dict.fromkeys(active))
        else:
            sequence = await self._historical_selection_sequence(db, game)
        if include_product_id:
            sequence.append(include_product_id)
        return list(dict.fromkeys(sequence))

    async def _current_selection_sequence(
        self,
        db: AsyncSession,
        game: dict[str, Any],
        include_product_id: str | None = None,
    ) -> list[str]:
        """Return onboarding + completed picks, optionally including a pending pick."""
        if self._is_redesigned_game(game):
            return await self._active_preference_sequence(db, game, include_product_id=include_product_id)
        return await self._historical_selection_sequence(db, game, include_product_id=include_product_id)

    def _top_preference_features(
        self,
        state: dict[str, Any],
        *,
        limit: int = 10,
    ) -> list[tuple[int, str, float]]:
        """Return the strongest positive learned preferences from the current state."""
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        inv_index = {v: k for k, v in self.recommender.feature_space.feature_index.items()}
        weighted: list[tuple[int, str, float]] = []
        for idx in range(len(user_vec)):
            weight = float(user_vec[idx])
            if weight <= 0.05:
                continue
            raw = inv_index.get(idx, f"feature_{idx}")
            weighted.append((idx, raw, weight))
        weighted.sort(key=lambda item: item[2], reverse=True)
        return weighted[:limit]

    def _predicted_match_features(
        self,
        state: dict[str, Any],
        product: dict[str, Any],
        *,
        limit: int = 5,
    ) -> list[str]:
        """Return the strongest preference clues this product matches."""
        item_vec = self.recommender.feature_space.vectorize(product)
        feature_pairs = self._top_preference_features(state, limit=max(limit * 2, 8))
        labels: list[str] = []
        seen: set[str] = set()
        for idx, raw, weight in feature_pairs:
            if idx >= len(item_vec) or item_vec[idx] == 0:
                continue
            if "::num::" in raw:
                label = numeric_preference_label(raw, weight)
            else:
                normalized_raw = raw.lower() if "::" in raw else raw
                humanized = profile_humanize_feature(normalized_raw)
                label = humanized or raw.replace("_", " ").title()
            if not label or "::" in label:
                continue
            if label.lower() in {"pens", "products", "fountain pens", "fountain pens type"}:
                continue
            key = label.lower()
            if key in seen:
                continue
            seen.add(key)
            labels.append(label)
            if len(labels) >= limit:
                break
        return labels

    async def _preference_deck(self, db: AsyncSession, game: dict[str, Any]) -> list[dict[str, Any]]:
        """Return visual cards for the current active preference deck."""
        category = self._game_category(game)
        preference_ids = await self._active_preference_sequence(db, game)
        products = await self._get_products_by_ids(
            db,
            preference_ids,
            projection=self._card_projection(category),
        )
        return [self._product_card(product, category) for product in products]

    def _game_out_payload(self, game: GameRecord | dict[str, Any], *, resumed: bool = False) -> dict[str, Any]:
        """Build a consistent game creation/resume payload."""
        record = record_to_dict(game) if isinstance(game, GameRecord) else dict(game)
        current_match_streak, longest_match_streak, match_streak_target = self._match_progress(record)
        return {
            "id": str(record["_id"]),
            "schema_version": int(record.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
            "player_name": record["player_name"],
            "category": self._game_category(record),
            "mode": record.get("mode") or "classic",
            "status": record["status"],
            "total_rounds": int(record.get("total_rounds") or self.DEFAULT_MATCH_STREAK_TARGET),
            "human_score": int(record.get("human_score") or 0),
            "ai_score": int(record.get("ai_score") or 0),
            "current_match_streak": current_match_streak,
            "longest_match_streak": longest_match_streak,
            "match_streak_target": match_streak_target,
            "rounds_played": self._rounds_played(record),
            "created_at": record["created_at"],
            "resumed": resumed,
        }

    async def _apply_seed_preferences_to_state(
        self,
        db: AsyncSession,
        model: PrefixCFModel,
        state: dict[str, Any],
        *,
        category: str,
        likes: dict[str, list[str]] | None = None,
        dislikes: dict[str, list[str]] | None = None,
        like_product_ids: list[str] | None = None,
        dislike_product_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply persisted seed preferences onto a mutable model state."""
        likes = likes or {}
        dislikes = dislikes or {}
        like_product_ids = like_product_ids or []
        dislike_product_ids = dislike_product_ids or []

        def build_seed_product(source: dict[str, list[str]]) -> dict[str, Any]:
            payload: dict[str, Any] = {"category": category}
            for key, values in source.items():
                if values:
                    payload[key] = values
            return payload

        if likes:
            product = build_seed_product(likes)
            model.update_with_seed(state, product, weight=0.45)

        if dislikes:
            product = build_seed_product(dislikes)
            model.update_with_negative_feedback(state, product, weight=0.45)
            tokens, _ = extract_feature_tokens(product, category)
            disliked_tokens = set(state.get("disliked_tokens") or [])
            disliked_tokens.update(tokens)
            state["disliked_tokens"] = list(disliked_tokens)

        if like_product_ids:
            products = await self._get_products_by_ids(
                db,
                like_product_ids,
                projection=self._feature_projection(category),
            )
            for product in products:
                model.update_with_seed(state, product, weight=0.6)

        if dislike_product_ids:
            products = await self._get_products_by_ids(
                db,
                dislike_product_ids,
                projection=self._feature_projection(category),
            )
            disliked_tokens = set(state.get("disliked_tokens") or [])
            for product in products:
                model.update_with_negative_feedback(state, product, weight=0.6)
                tokens, _ = extract_feature_tokens(product, category)
                disliked_tokens.update(tokens)
            state["disliked_tokens"] = list(disliked_tokens)

        return state

    async def _metrics_for_state(
        self,
        db: AsyncSession,
        model: PrefixCFModel,
        state: dict[str, Any],
        selected_ids: list[str],
        category: str,
    ) -> dict[str, float]:
        """Compute coherence and predicted prefix rating for selected products."""
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
        """Load and cache all products for a category used in scoring/ranking."""
        current_count = await db.scalar(
            select(func.count()).select_from(ProductRecord).where(ProductRecord.category == category)
        )
        cached = self._scoring_catalog_cache.get(category)
        if cached and cached.get("count") == int(current_count or 0):
            return cached["products"]
        rows = (await db.execute(select(ProductRecord).where(ProductRecord.category == category))).scalars().all()
        products = self._filter_visible_products([record_to_dict(row) for row in rows], category)
        self._scoring_catalog_cache[category] = {
            "count": int(current_count or 0),
            "products": products,
            "loaded_at": datetime.utcnow(),
        }
        return products

    async def _all_products_for_onboarding_sample(self, db: AsyncSession, category: str) -> list[dict[str, Any]]:
        """Load all products for onboarding sampling (no caching)."""
        rows = (await db.execute(select(ProductRecord).where(ProductRecord.category == category))).scalars().all()
        return self._filter_visible_products([record_to_dict(row) for row in rows], category)

    async def _warm_scoring_catalog(self, db: AsyncSession, category: str) -> None:
        """Best-effort cache warmup to reduce first-round latency."""
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
        """Create a deterministic, diverse onboarding pool."""
        target_size = int(get_category_profile(category).onboarding_pool_size or 100)
        if len(all_products) <= target_size:
            return [str(p["_id"]) for p in all_products]
        rng = self._rng_for(game_id, 0, "onboarding")
        products = list(all_products)
        rng.shuffle(products)
        profile = get_category_profile(category)
        values_by_field: dict[str, list[float]] = {}
        for field in profile.numeric_fields:
            values: list[float] = []
            for p in products:
                raw = p.get(field)
                try:
                    if raw is not None:
                        values.append(float(raw))
                except (TypeError, ValueError):
                    continue
            if len(values) >= 10:
                values_by_field[field] = values

        if not values_by_field:
            # If a category has no usable numeric signal, keep deterministic sampling
            # and return a shuffled subset rather than failing the game start flow.
            return [str(p["_id"]) for p in products[:target_size]]

        # Pick the numeric axis with highest spread so low/mid/high buckets are meaningful.
        numeric_field = max(
            values_by_field.keys(),
            key=lambda field: max(values_by_field[field]) - min(values_by_field[field]),
        )
        values = [float(p.get(numeric_field) or 0.0) for p in products]
        sorted_values = sorted(values)
        quantile_boundaries = [
            sorted_values[int(len(sorted_values) * ratio)]
            for ratio in (0.2, 0.4, 0.6, 0.8)
        ]
        buckets: list[list[dict[str, Any]]] = [[] for _ in range(5)]
        for p in products:
            value = float(p.get(numeric_field) or 0.0)
            bucket_index = 4
            for idx, boundary in enumerate(quantile_boundaries):
                if value <= boundary:
                    bucket_index = idx
                    break
            buckets[bucket_index].append(p)

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
            # Cycle vendor-by-vendor so one studio/brand does not dominate onboarding.
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

        chosen: list[dict[str, Any]] = []
        per_bucket = max(1, target_size // max(len(buckets), 1))
        for index, bucket in enumerate(buckets):
            remaining = max(0, target_size - len(chosen))
            if remaining <= 0:
                break
            bucket_target = per_bucket if index < len(buckets) - 1 else remaining
            chosen.extend(round_robin_pick(bucket, min(bucket_target, remaining)))
        chosen_ids = {str(p["_id"]) for p in chosen}
        if len(chosen) < target_size:
            remainder = [p for p in products if str(p["_id"]) not in chosen_ids]
            rng.shuffle(remainder)
            chosen.extend(remainder[: target_size - len(chosen)])
        chosen = chosen[:target_size]
        rng.shuffle(chosen)
        return [str(p["_id"]) for p in chosen]

    def _seeded_onboarding_sample(
        self,
        all_products: list[dict[str, Any]],
        game_id: str,
        category: str,
        model: PrefixCFModel,
        state: dict[str, Any],
    ) -> list[str]:
        """Create a large onboarding pool biased by seed preferences."""
        target_size = int(get_category_profile(category).onboarding_pool_size or 100)
        if len(all_products) <= target_size:
            return [str(p["_id"]) for p in all_products]
        rng = self._rng_for(game_id, 0, "onboarding_seeded")
        disliked_tokens = set(state.get("disliked_tokens") or [])
        scored = self._rank_candidates(model, state, all_products, category, disliked_tokens)

        likely_cutoff = min(len(scored), max(target_size, int(target_size * 1.2)))
        likely = scored[:likely_cutoff]
        tail = scored[likely_cutoff:]

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

        add_from_pool(likely, max(1, int(target_size * 0.55)))
        add_from_pool(tail, target_size)
        if len(selected_ids) < target_size:
            remainder = [str(p["_id"]) for _, p in scored if str(p["_id"]) not in selected_set]
            rng.shuffle(remainder)
            selected_ids.extend(remainder[: target_size - len(selected_ids)])

        selected_ids = selected_ids[:target_size]
        rng.shuffle(selected_ids)
        return selected_ids

    def _rank_candidates(
        self,
        model: PrefixCFModel,
        state: dict[str, Any],
        products: list[dict[str, Any]],
        category: str,
        disliked_tokens: set[str] | None = None,
    ) -> list[tuple[float, dict[str, Any]]]:
        """Score and rank products against current user preference state."""
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
            if disliked_tokens:
                tokens, _ = extract_feature_tokens(product, category)
                overlap = len(disliked_tokens.intersection(tokens))
                if overlap:
                    score -= min(1.0, overlap * 0.15)
            score = float(min(5.0, max(1.0, score)))
            scored.append((score, product))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)
        return scored

    def _build_round_candidates(
        self,
        game_id: str,
        round_number: int,
        category: str,
        scored: list[tuple[float, dict[str, Any]]],
    ) -> list[str]:
        """Build a category-aware candidate set for the next round."""
        rng = self._rng_for(game_id, round_number, "round_candidates")
        target = self._round_candidate_target(category)

        if target == 2:
            return self._build_round_duel_candidates(rng, scored)

        if len(scored) <= target:
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

        # Mix likely picks, borderline picks, and harder/distant picks to avoid
        # overly easy rounds while still keeping AI-scorable candidates.
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
        selected_ids = selected_ids[:target]
        rng.shuffle(selected_ids)
        return selected_ids

    @staticmethod
    def _build_round_duel_candidates(
        rng: random.Random,
        scored: list[tuple[float, dict[str, Any]]],
    ) -> list[str]:
        """Build a two-item duel from one likely and one close-rank challenger."""
        if len(scored) <= 2:
            ids = [str(p["_id"]) for _, p in scored]
            rng.shuffle(ids)
            return ids

        top_pool = scored[: min(12, len(scored))]
        _, anchor = rng.choice(top_pool)
        anchor_id = str(anchor["_id"])

        ranked_ids = [str(p["_id"]) for _, p in scored]
        anchor_rank = ranked_ids.index(anchor_id)
        near_start = max(0, anchor_rank - 8)
        near_end = min(len(scored), anchor_rank + 9)
        near_pool = [pair for pair in scored[near_start:near_end] if str(pair[1]["_id"]) != anchor_id]
        if not near_pool:
            near_pool = [pair for pair in scored if str(pair[1]["_id"]) != anchor_id]

        _, challenger = rng.choice(near_pool)
        ids = [anchor_id, str(challenger["_id"])]
        rng.shuffle(ids)
        return ids

    async def get_categories(self, db: AsyncSession) -> list[dict[str, Any]]:
        """Return configured categories with currently available product counts."""
        rows = (await db.execute(select(ProductRecord.category, ProductRecord.data))).all()
        counts: dict[str, int] = {}
        for category, data in rows:
            normalized_category = str(category or "")
            product = {"category": normalized_category, **dict(data or {})}
            if not self._filter_visible_products([product], normalized_category):
                continue
            counts[normalized_category] = counts.get(normalized_category, 0) + 1
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
        mode: str = "classic",
        total_rounds: int = 5,
        fresh_start: bool = False,
    ) -> dict[str, Any]:
        """Create and persist a new game session for a player/category."""
        await self._ensure_indexes(db)
        model = await self._ensure_model(db)
        normalized_category = normalize_category(category)
        normalized_mode = self._normalize_mode(mode)
        clean_name = player_name.strip()
        if not clean_name:
            raise ValueError("Player name is required")
        now = datetime.utcnow()
        active_game = await db.scalar(
            select(GameRecord)
            .where(
                and_(
                    GameRecord.player_name == clean_name,
                    GameRecord.category == normalized_category,
                    GameRecord.status.in_(["onboarding", "ready", "playing"]),
                )
            )
            .order_by(GameRecord.updated_at.desc(), GameRecord.created_at.desc())
            .limit(1)
        )
        latest_completed_game = await db.scalar(
            select(GameRecord)
            .where(
                and_(
                    GameRecord.player_name == clean_name,
                    GameRecord.category == normalized_category,
                    GameRecord.status == "completed",
                )
            )
            .order_by(GameRecord.updated_at.desc(), GameRecord.created_at.desc())
            .limit(1)
        )
        if active_game is not None:
            if fresh_start:
                await db.execute(delete(GameRoundRecord).where(GameRoundRecord.game_id == active_game.id))
                await db.execute(delete(PrefixRatingRecord).where(PrefixRatingRecord.session_id == active_game.id))
                active_game.status = "onboarding"
                active_game.current_round = 0
                active_game.total_rounds = self.DEFAULT_MATCH_STREAK_TARGET
                active_game.human_score = 0
                active_game.ai_score = 0
                active_game.mode = normalized_mode
                active_game.schema_version = self.REDESIGN_SCHEMA_VERSION
                active_game.model_state = self._ensure_redesign_state(model.init_state())
                active_game.onboarding_pool_ids = []
                active_game.onboarding_selected_ids = []
                active_game.onboarding_rating = None
                active_game.updated_at = now
                await db.commit()
                await db.refresh(active_game)
                return self._game_out_payload(active_game, resumed=False)

            if int(active_game.schema_version or self.LEGACY_SCHEMA_VERSION) < self.REDESIGN_SCHEMA_VERSION:
                active_game.schema_version = self.REDESIGN_SCHEMA_VERSION
                active_game.total_rounds = self.DEFAULT_MATCH_STREAK_TARGET
                active_game.model_state = self._ensure_redesign_state(active_game.model_state or model.init_state())
                active_game.updated_at = now
                await db.commit()
                await db.refresh(active_game)
            return self._game_out_payload(active_game, resumed=True)

        if fresh_start:
            game = GameRecord(
                schema_version=self.REDESIGN_SCHEMA_VERSION,
                player_name=clean_name,
                category=normalized_category,
                mode=normalized_mode,
                status="onboarding",
                current_round=0,
                total_rounds=self.DEFAULT_MATCH_STREAK_TARGET,
                human_score=0,
                ai_score=0,
                model_state=self._ensure_redesign_state(model.init_state()),
                onboarding_pool_ids=[],
                onboarding_selected_ids=[],
                onboarding_rating=None,
                created_at=now,
                updated_at=now,
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)
            return self._game_out_payload(game, resumed=False)

        if self._has_carryable_profile(latest_completed_game):
            game = GameRecord(
                schema_version=self.REDESIGN_SCHEMA_VERSION,
                player_name=clean_name,
                category=normalized_category,
                mode=normalized_mode,
                status="ready",
                current_round=0,
                total_rounds=self.DEFAULT_MATCH_STREAK_TARGET,
                human_score=0,
                ai_score=0,
                model_state=self._reset_run_progress(latest_completed_game.model_state or model.init_state()),
                onboarding_pool_ids=[],
                onboarding_selected_ids=list(latest_completed_game.onboarding_selected_ids or []),
                onboarding_rating=latest_completed_game.onboarding_rating,
                created_at=now,
                updated_at=now,
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)
            return self._game_out_payload(game, resumed=False)

        if latest_completed_game is not None:
            game = GameRecord(
                schema_version=self.REDESIGN_SCHEMA_VERSION,
                player_name=clean_name,
                category=normalized_category,
                mode=normalized_mode,
                status="onboarding",
                current_round=0,
                total_rounds=self.DEFAULT_MATCH_STREAK_TARGET,
                human_score=0,
                ai_score=0,
                model_state=self._ensure_redesign_state(model.init_state()),
                onboarding_pool_ids=[],
                onboarding_selected_ids=[],
                onboarding_rating=None,
                created_at=now,
                updated_at=now,
            )
            db.add(game)
            await db.commit()
            await db.refresh(game)
            return self._game_out_payload(game, resumed=False)

        game = GameRecord(
            schema_version=self.REDESIGN_SCHEMA_VERSION,
            player_name=clean_name,
            category=normalized_category,
            mode=normalized_mode,
            status="onboarding",
            current_round=0,
            total_rounds=self.DEFAULT_MATCH_STREAK_TARGET,
            human_score=0,
            ai_score=0,
            model_state=self._ensure_redesign_state(model.init_state()),
            onboarding_pool_ids=[],
            onboarding_selected_ids=[],
            onboarding_rating=None,
            created_at=now,
            updated_at=now,
        )
        db.add(game)
        await db.commit()
        await db.refresh(game)
        return self._game_out_payload(game, resumed=False)

    async def submit_feedback(
        self,
        db: AsyncSession,
        game_id: str,
        product_id: str,
        action: str,
    ) -> dict[str, Any]:
        """Apply beta feedback signals such as 'less like this'."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)
        mode = self._normalize_mode(game.get("mode"))
        if mode != "beta":
            raise ValueError("Feedback is only available in beta mode")

        normalized_action = str(action or "").strip().lower()
        if normalized_action != "less_like_this":
            raise ValueError("Unsupported feedback action")

        products = await self._get_products_by_ids(
            db,
            [product_id],
            projection=self._feature_projection(category),
        )
        if not products:
            raise ValueError("Selected product does not exist")

        product = products[0]
        state = self._ensure_redesign_state(game.get("model_state") or model.init_state())
        self._align_state_to_feature_space(model, state)
        model.update_with_negative_feedback(state, product)

        disliked_ids = set(state.get("disliked_ids") or [])
        disliked_ids.add(product_id)
        state["disliked_ids"] = list(disliked_ids)

        tokens, _ = extract_feature_tokens(product, category)
        disliked_tokens = set(state.get("disliked_tokens") or [])
        disliked_tokens.update(tokens)
        state["disliked_tokens"] = list(disliked_tokens)

        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.model_state = state
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {
            "accepted": True,
            "action": normalized_action,
            "product_id": product_id,
        }

    async def submit_seed_preferences(
        self,
        db: AsyncSession,
        game_id: str,
        likes: dict[str, list[str]] | None = None,
        dislikes: dict[str, list[str]] | None = None,
        like_product_ids: list[str] | None = None,
        dislike_product_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Apply beta seed preferences before onboarding."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)
        mode = self._normalize_mode(game.get("mode"))
        if mode != "beta":
            raise ValueError("Seeding is only available in beta mode")

        likes = likes or {}
        dislikes = dislikes or {}
        like_product_ids = like_product_ids or []
        dislike_product_ids = dislike_product_ids or []

        state = self._ensure_redesign_state(game.get("model_state") or model.init_state())
        self._align_state_to_feature_space(model, state)
        state = await self._apply_seed_preferences_to_state(
            db,
            model,
            state,
            category=category,
            likes=likes,
            dislikes=dislikes,
            like_product_ids=like_product_ids,
            dislike_product_ids=dislike_product_ids,
        )

        state["seeded"] = True
        state["seed_preferences"] = {
            "likes": likes,
            "dislikes": dislikes,
            "like_product_ids": like_product_ids,
            "dislike_product_ids": dislike_product_ids,
        }

        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.model_state = state
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {"accepted": True}

    async def update_preferences(
        self,
        db: AsyncSession,
        game_id: str,
        *,
        active_preference_ids: list[str],
    ) -> dict[str, Any]:
        """Rebuild the active preference deck and refresh the live round if needed."""
        game = await self._get_game(db, game_id)
        if not self._is_redesigned_game(game):
            raise ValueError("Preference editing is only available for redesigned sessions")
        onboarding_count = len(game.get("onboarding_selected_ids") or [])
        if not self.MIN_ONBOARDING_SELECTIONS <= onboarding_count <= self.MAX_ONBOARDING_SELECTIONS:
            raise ValueError("Onboarding must be completed before editing preferences")

        model = await self._ensure_model(db)
        category = self._game_category(game)
        current_state = self._ensure_redesign_state(game.get("model_state") or model.init_state())
        allowed_ids = set(await self._historical_selection_sequence(db, game))
        cleaned_ids = list(dict.fromkeys(str(pid) for pid in active_preference_ids if str(pid) in allowed_ids))
        if not cleaned_ids:
            raise ValueError("Keep at least one preference in your deck")

        rebuilt_state = self._ensure_redesign_state(model.init_state())
        self._align_state_to_feature_space(model, rebuilt_state)
        seed_preferences = current_state.get("seed_preferences") or self._empty_seed_preferences()
        await self._apply_seed_preferences_to_state(
            db,
            model,
            rebuilt_state,
            category=category,
            likes=seed_preferences.get("likes") or {},
            dislikes=seed_preferences.get("dislikes") or {},
            like_product_ids=seed_preferences.get("like_product_ids") or [],
            dislike_product_ids=seed_preferences.get("dislike_product_ids") or [],
        )

        preference_products = await self._get_products_by_ids(
            db,
            cleaned_ids,
            projection=self._feature_projection(category),
        )
        if len(preference_products) != len(cleaned_ids):
            raise ValueError("One or more selected preferences no longer exist")

        for product in preference_products:
            model.update_with_selection(rebuilt_state, product, is_exception=False)
        if game.get("onboarding_rating") is not None:
            model.update_with_prefix_rating(rebuilt_state, int(game["onboarding_rating"]))

        rebuilt_state["active_preference_ids"] = cleaned_ids
        rebuilt_state["seed_preferences"] = seed_preferences
        rebuilt_state["seeded"] = bool(current_state.get("seeded"))
        rebuilt_state["disliked_ids"] = list(current_state.get("disliked_ids") or [])
        rebuilt_state["disliked_tokens"] = list(current_state.get("disliked_tokens") or [])
        rebuilt_state["rounds_played"] = int(current_state.get("rounds_played") or game.get("current_round") or 0)
        rebuilt_state["total_matches"] = int(current_state.get("total_matches") or game.get("human_score") or 0)
        rebuilt_state["current_match_streak"] = int(current_state.get("current_match_streak") or 0)
        rebuilt_state["longest_match_streak"] = int(current_state.get("longest_match_streak") or 0)
        rebuilt_state["match_streak_target"] = int(
            current_state.get("match_streak_target") or self.DEFAULT_MATCH_STREAK_TARGET
        )

        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.model_state = rebuilt_state
            game_row.updated_at = datetime.utcnow()

        active_round = await db.scalar(
            select(GameRoundRecord).where(
                and_(
                    GameRoundRecord.game_id == str(game["_id"]),
                    GameRoundRecord.round_number == int(game.get("current_round") or 0) + 1,
                    GameRoundRecord.completed.is_(False),
                )
            )
        )
        if active_round is not None:
            await db.delete(active_round)

        await db.commit()

        updated_game = {**game, "model_state": rebuilt_state}
        round_payload = None
        if game.get("status") == "playing":
            round_payload = await self.start_round(db, game_id)

        return {
            "game_id": str(game["_id"]),
            "schema_version": self.REDESIGN_SCHEMA_VERSION,
            "category": category,
            "category_copy": category_copy(category),
            "display_schema": category_display_schema(category),
            "preference_deck": await self._preference_deck(db, updated_game),
            "current_match_streak": int(rebuilt_state.get("current_match_streak") or 0),
            "longest_match_streak": int(rebuilt_state.get("longest_match_streak") or 0),
            "match_streak_target": int(rebuilt_state.get("match_streak_target") or self.DEFAULT_MATCH_STREAK_TARGET),
            "rounds_played": int(rebuilt_state.get("rounds_played") or 0),
            "round": round_payload,
        }

    async def get_resume_state(
        self,
        db: AsyncSession,
        player_name: str,
        category: str = "fountain_pens",
    ) -> dict[str, Any]:
        """Return whether a resumable game exists for player+category."""
        normalized_category = normalize_category(category)
        clean_name = player_name.strip()
        if not clean_name:
            return {
                "exists": False,
                "can_start_fresh": False,
                "game_id": None,
                "player_name": None,
                "category": normalized_category,
                "status": None,
                "current_round": None,
                "total_rounds": None,
            }
        any_game = await db.scalar(
            select(GameRecord)
            .where(
                and_(
                    GameRecord.player_name == clean_name,
                    GameRecord.category == normalized_category,
                )
            )
            .limit(1)
        )
        active_game = await db.scalar(
            select(GameRecord)
            .where(
                and_(
                    GameRecord.player_name == clean_name,
                    GameRecord.category == normalized_category,
                    GameRecord.status.in_(["onboarding", "ready", "playing"]),
                )
            )
            .order_by(GameRecord.updated_at.desc(), GameRecord.created_at.desc())
            .limit(1)
        )
        if active_game is None:
            return {
                "exists": False,
                "can_start_fresh": any_game is not None,
                "game_id": None,
                "player_name": clean_name,
                "category": normalized_category,
                "status": None,
                "current_round": None,
                "total_rounds": None,
            }
        return {
            "exists": True,
            "can_start_fresh": True,
            "game_id": active_game.id,
            "player_name": active_game.player_name,
            "category": normalized_category,
            "status": active_game.status,
            "current_round": int(active_game.current_round or 0),
            "total_rounds": int(active_game.total_rounds or 0),
        }


game_service = GameService()
