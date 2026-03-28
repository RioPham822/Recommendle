"""Gameplay round lifecycle logic for onboarding, candidate generation, and pick submission."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..category_profiles import (
    category_display_schema,
    category_copy,
    get_category_profile,
    extract_feature_tokens,
)
from ..category_profiles import humanize_feature as profile_humanize_feature
from ..category_profiles import humanize_feature_list as profile_humanize_feature_list
from ..category_profiles import (
    numeric_preference_label,
)
from ..db import GameRecord, GameRoundRecord, PrefixRatingRecord


def humanize_feature(raw: str) -> str | None:
    """Convert a raw feature token into a UI-friendly label."""
    return profile_humanize_feature(raw)


def humanize_feature_list(raw_list: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Convert and deduplicate feature labels for display."""
    return profile_humanize_feature_list(raw_list)


class GamePlayMixin:
    """Composable gameplay operations used by the main game service."""

    async def get_onboarding(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        """Return or create the onboarding pool for a game."""
        game = await self._get_game(db, game_id)
        category = self._game_category(game)
        if game.get("status") == "completed":
            raise ValueError("Game is already completed")

        pool_ids = game.get("onboarding_pool_ids") or []
        if not pool_ids:
            all_products = await self._all_products_for_onboarding_sample(db, category)
            mode = str(game.get("mode") or "classic").lower()
            if mode == "beta":
                model = await self._ensure_model(db)
                state = game.get("model_state") or model.init_state()
                self._align_state_to_feature_space(model, state)
                has_seed = bool(state.get("seeded"))
                has_signal = any(abs(v) > 0.01 for v in state.get("user_vec", []))
                if has_seed or has_signal:
                    pool_ids = self._seeded_onboarding_sample(all_products, game_id, category, model, state)
                else:
                    pool_ids = self._diverse_onboarding_sample(all_products, game_id, category)
            else:
                pool_ids = self._diverse_onboarding_sample(all_products, game_id, category)
            game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
            if game_row:
                game_row.onboarding_pool_ids = pool_ids
                game_row.updated_at = datetime.utcnow()
                await db.commit()

        await self._warm_scoring_catalog(db, category)

        products = await self._get_products_by_ids(
            db,
            pool_ids,
            projection=self._card_projection(category),
        )

        return {
            "game_id": game_id,
            "category": category,
            "category_copy": category_copy(category),
            "display_schema": category_display_schema(category),
            "pool_size": len(products),
            "products": [self._product_card(p, category) for p in products],
        }

    async def submit_onboarding(
        self,
        db: AsyncSession,
        game_id: str,
        selected_product_ids: list[str],
        rating: int,
    ) -> dict[str, Any]:
        """Persist onboarding picks/rating and initialize model state for round play."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)

        if game.get("onboarding_selected_ids"):
            raise ValueError("Onboarding already submitted for this game")
        if len(selected_product_ids) != 10:
            raise ValueError("You must select exactly 10 products")
        if len(set(selected_product_ids)) != 10:
            raise ValueError("Duplicate products are not allowed")

        pool_ids = set(game.get("onboarding_pool_ids", []))
        if not pool_ids:
            raise ValueError("Onboarding pool is not initialized")
        if any(pid not in pool_ids for pid in selected_product_ids):
            raise ValueError("Selections must come from the onboarding pool")

        selected_products = await self._get_products_by_ids(
            db,
            selected_product_ids,
            projection={**self._feature_projection(category), "title": 1, "images": 1},
        )
        if len(selected_products) != 10:
            raise ValueError("One or more selected products were not found")

        state = game.get("model_state") or model.init_state()
        self._align_state_to_feature_space(model, state)
        for product in selected_products:
            model.update_with_selection(state, product, is_exception=False)
        model.update_with_prefix_rating(state, rating)
        metrics = await self._metrics_for_state(db, model, state, selected_product_ids, category)

        db.add(
            PrefixRatingRecord(
                session_id=str(game["_id"]),
                rating=int(rating),
                tags=[],
                created_at=datetime.utcnow(),
            )
        )
        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.status = "ready"
            game_row.category = category
            game_row.model_state = state
            game_row.onboarding_selected_ids = selected_product_ids
            game_row.onboarding_rating = int(rating)
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {
            "accepted": True,
            "coherence_score": metrics["coherence_score"],
            "predicted_prefix_rating": metrics["predicted_prefix_rating"],
            "next_round": 1,
        }

    async def start_round(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        """Start the next round and return its candidate cards."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)

        if len(game.get("onboarding_selected_ids", [])) != 10:
            raise ValueError("Onboarding is incomplete")
        if game["current_round"] >= game["total_rounds"]:
            raise ValueError("Game is complete")

        round_number = game["current_round"] + 1
        round_target = self._round_candidate_target(category)
        existing = await db.scalar(
            select(GameRoundRecord).where(
                and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.round_number == round_number)
            )
        )
        if existing and not existing.completed:
            products = await self._get_products_by_ids(
                db,
                existing.candidate_ids or [],
                projection=self._card_projection(category),
            )
            return {
                "round_number": round_number,
                "category": category,
                "round_mode": get_category_profile(category).round_mode,
                "category_copy": category_copy(category),
                "display_schema": category_display_schema(category),
                "candidates": [self._product_card(p, category) for p in products],
                "pre_round_metrics": existing.pre_metrics or {"coherence_score": 0.0, "predicted_prefix_rating": 3.0},
            }

        state = game.get("model_state") or model.init_state()
        if self._align_state_to_feature_space(model, state):
            game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
            if game_row:
                game_row.model_state = state
                game_row.updated_at = datetime.utcnow()
                await db.commit()

        selected_ids = await self._current_selection_sequence(db, game)
        used = set(selected_ids)
        disliked_ids = set(state.get("disliked_ids") or [])
        disliked_tokens = set(state.get("disliked_tokens") or [])
        all_products = await self._all_products_for_scoring(db, category)
        candidates_source = [
            p for p in all_products if str(p["_id"]) not in used and str(p["_id"]) not in disliked_ids
        ]
        if len(candidates_source) < 10:
            raise ValueError("Not enough products left to generate a round")

        scored = self._rank_candidates(model, state, candidates_source, category, disliked_tokens)
        candidate_ids = self._build_round_candidates(game_id, round_number, category, scored)
        candidate_products = await self._get_products_by_ids(
            db,
            candidate_ids,
            projection=self._card_projection(category),
        )
        pre_metrics = await self._metrics_for_state(db, model, state, selected_ids, category)

        if existing is None:
            db.add(
                GameRoundRecord(
                    schema_version=2,
                    category=category,
                    game_id=str(game["_id"]),
                    round_number=round_number,
                    candidate_ids=candidate_ids,
                    pre_metrics=pre_metrics,
                    completed=False,
                    created_at=datetime.utcnow(),
                )
            )
        else:
            existing.candidate_ids = candidate_ids
            existing.pre_metrics = pre_metrics
            existing.completed = False

        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.status = "playing"
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {
            "round_number": round_number,
            "category": category,
            "round_mode": get_category_profile(category).round_mode,
            "category_copy": category_copy(category),
            "display_schema": category_display_schema(category),
            "candidates": [self._product_card(p, category) for p in candidate_products],
            "pre_round_metrics": pre_metrics,
        }

    async def submit_pick(
        self,
        db: AsyncSession,
        game_id: str,
        round_number: int,
        product_id: str,
        less_like_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Score a human pick against AI predictions and finalize round state."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)
        profile = get_category_profile(category)
        duel_mode = profile.round_mode == "duel"

        if game["current_round"] >= game["total_rounds"]:
            raise ValueError("Game is already complete")
        if round_number != game["current_round"] + 1:
            raise ValueError("Invalid round number for current game state")

        round_row = await db.scalar(
            select(GameRoundRecord).where(
                and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.round_number == round_number)
            )
        )
        if round_row is None:
            raise ValueError("Round has not been started")
        if round_row.completed:
            raise ValueError("Round has already been completed")

        candidate_ids = round_row.candidate_ids or []
        if product_id not in candidate_ids:
            raise ValueError("Selected product is not in this round's candidate set")

        candidate_products = await self._get_products_by_ids(
            db,
            candidate_ids,
            projection={**self._feature_projection(category), "title": 1, "images": 1},
        )
        by_id = {str(p["_id"]): p for p in candidate_products}
        if product_id not in by_id:
            raise ValueError("Selected product does not exist")

        state = game.get("model_state") or model.init_state()
        self._align_state_to_feature_space(model, state)
        less_like_ids = [pid for pid in (less_like_ids or []) if pid != product_id]
        if less_like_ids:
            products = await self._get_products_by_ids(
                db,
                less_like_ids,
                projection=self._feature_projection(category),
            )
            disliked_ids = set(state.get("disliked_ids") or [])
            disliked_tokens = set(state.get("disliked_tokens") or [])
            for product in products:
                pid = str(product.get("_id"))
                disliked_ids.add(pid)
                model.update_with_negative_feedback(state, product, weight=0.6)
                tokens, _ = extract_feature_tokens(product, category)
                disliked_tokens.update(tokens)
            state["disliked_ids"] = list(disliked_ids)
            state["disliked_tokens"] = list(disliked_tokens)
        item_vectors = self.recommender.item_vectors
        item_norms = self.recommender.item_norms
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        user_norm = float(np.linalg.norm(user_vec))
        bias = float(state.get("bias", 0.0))
        scored = []
        for item in candidate_products:
            pid = str(item["_id"])
            vec = item_vectors.get(pid)
            if vec is None:
                vec = self.recommender.feature_space.vectorize(item)
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
            scored.append((score, item))
        scored.sort(key=lambda item: (item[0], str(item[1]["_id"])), reverse=True)

        ai_score, ai_pick_product = scored[0]
        ai_pick_id = str(ai_pick_product["_id"])
        ai_top3_ids = [str(p["_id"]) for _, p in scored[:3]]
        ai_exact = ai_pick_id == product_id
        ai_correct = ai_exact if duel_mode else (product_id in ai_top3_ids)
        human_points = 0 if ai_correct else 10
        ai_points = 10 if ai_correct else 0
        ai_rank_of_pick = next((i + 1 for i, (_, p) in enumerate(scored) if str(p["_id"]) == product_id), len(scored))

        human_pick_product = by_id[product_id]
        model.update_with_selection(state, human_pick_product, is_exception=False)
        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.model_state = state

        selected_ids = await self._current_selection_sequence(db, game, include_product_id=product_id)
        post_metrics = await self._metrics_for_state(db, model, state, selected_ids, category)

        top_candidates = []
        for score, product in scored[:5]:
            card = self._product_card(product, category)
            card["score"] = float(score)
            top_candidates.append(card)

        human_vec = self.recommender.feature_space.vectorize(human_pick_product)
        ai_vec = self.recommender.feature_space.vectorize(ai_pick_product)
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)

        inv_index = {v: k for k, v in self.recommender.feature_space.feature_index.items()}
        feature_weights = []
        for idx in range(len(user_vec)):
            w = float(user_vec[idx])
            if abs(w) > 0.05:
                fname = inv_index.get(idx, f"feature_{idx}")
                if "::num::" in fname:
                    feature_weights.append((numeric_preference_label(fname, w), abs(w)))
                else:
                    feature_weights.append((fname, w))
        feature_weights.sort(key=lambda x: abs(x[1]), reverse=True)
        top_positive = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w > 0][:8])
        top_negative = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w < 0][:5])

        human_features = [inv_index.get(i, f"f{i}") for i in range(len(human_vec)) if human_vec[i] > 0]
        ai_features = [inv_index.get(i, f"f{i}") for i in range(len(ai_vec)) if ai_vec[i] > 0]
        shared_raw = list(set(human_features) & set(ai_features))
        shared_features = [h for h in (humanize_feature(f) for f in shared_raw) if h is not None]

        all_selected_ids = await self._current_selection_sequence(db, game, include_product_id=product_id)
        all_selected_products = await self._get_products_by_ids(
            db,
            all_selected_ids,
            projection=self._feature_projection(category),
        )
        hidden_raw = model.detect_hidden_preferences(state, all_selected_products)
        hidden_prefs = humanize_feature_list([(h["feature"], round(h["latency"], 3)) for h in hidden_raw])
        hidden_hints: list[str] = []
        for h in hidden_raw[:2]:
            label = humanize_feature(h["feature"])
            if label:
                hidden_hints.append(
                    f'The AI notices a hidden pattern: your picks tend to share "{label}" '
                    f"even though you may not have targeted it."
                )

        if ai_correct:
            if ai_exact:
                if duel_mode:
                    reason = (
                        f"The AI won this duel and matched your exact {profile.item_singular} choice. "
                        f"It predicted your side correctly from the two options shown."
                    )
                else:
                    reason = (
                        f"The AI predicted your exact {profile.item_singular}! "
                        f"It ranked this title #1 out of {len(candidate_products)} candidates based on your preference profile."
                    )
            else:
                match_rank = ai_top3_ids.index(product_id) + 1
                reason = (
                    f"Your pick was the AI's #{match_rank} prediction. "
                    f"The AI successfully identified your choice within its top 3 candidates."
                )
        else:
            reason = (
                f"Your pick ranked #{ai_rank_of_pick} in the AI's predictions. "
                f"The model's top pick was '{ai_pick_product.get('title', 'Unknown')}', "
                f"which scored {ai_score:.2f} based on feature similarity to your profile."
            )

        round_row.schema_version = 2
        round_row.human_pick_id = product_id
        round_row.ai_pick_id = ai_pick_id
        round_row.ai_confidence = float(ai_score)
        round_row.ai_top_k = [{"product_id": str(product["_id"]), "score": float(score)} for score, product in scored[:5]]
        round_row.ai_top3_ids = ai_top3_ids
        round_row.ai_rank_of_pick = ai_rank_of_pick
        round_row.ai_correct = ai_correct
        round_row.human_points = human_points
        round_row.ai_points = ai_points
        round_row.post_metrics = post_metrics
        round_row.completed = True
        round_row.completed_at = datetime.utcnow()

        new_current_round = game["current_round"] + 1
        new_human_total = game["human_score"] + human_points
        new_ai_total = game["ai_score"] + ai_points
        game_complete = new_current_round >= game["total_rounds"]

        if game_row:
            game_row.current_round = new_current_round
            game_row.human_score = new_human_total
            game_row.ai_score = new_ai_total
            game_row.status = "completed" if game_complete else "playing"
            game_row.model_state = state
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {
            "round_number": round_number,
            "category": category,
            "round_mode": profile.round_mode,
            "category_copy": category_copy(category),
            "human_pick": self._product_card(human_pick_product, category),
            "ai_pick": {**self._product_card(ai_pick_product, category), "score": float(ai_score)},
            "ai_correct": ai_correct,
            "ai_exact": ai_exact,
            "ai_rank_of_pick": ai_rank_of_pick,
            "ai_top3_ids": ai_top3_ids,
            "human_points": human_points,
            "ai_points": ai_points,
            "total_human_score": new_human_total,
            "total_ai_score": new_ai_total,
            "ai_explanation": {
                "reason": reason,
                "top_candidates": top_candidates,
                "learned_preferences": top_positive,
                "learned_dislikes": top_negative,
                "shared_features": shared_features[:6],
                "hidden_preferences": hidden_prefs,
                "hidden_preference_hints": hidden_hints,
            },
            "post_round_metrics": post_metrics,
            "game_complete": game_complete,
        }

    async def refresh_round(
        self,
        db: AsyncSession,
        game_id: str,
        *,
        less_like_ids: list[str] | None = None,
    ) -> dict[str, Any]:
        """Refresh current round with a new candidate set."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)

        if len(game.get("onboarding_selected_ids", [])) != 10:
            raise ValueError("Onboarding is incomplete")
        if game["current_round"] >= game["total_rounds"]:
            raise ValueError("Game is complete")

        round_number = game["current_round"] + 1
        round_row = await db.scalar(
            select(GameRoundRecord).where(
                and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.round_number == round_number)
            )
        )
        if round_row is None or round_row.completed:
            raise ValueError("Round is not active")

        state = game.get("model_state") or model.init_state()
        self._align_state_to_feature_space(model, state)

        less_like_ids = list(dict.fromkeys(less_like_ids or []))
        if less_like_ids:
            products = await self._get_products_by_ids(
                db,
                less_like_ids,
                projection=self._feature_projection(category),
            )
            disliked_ids = set(state.get("disliked_ids") or [])
            disliked_tokens = set(state.get("disliked_tokens") or [])
            for product in products:
                pid = str(product.get("_id"))
                disliked_ids.add(pid)
                model.update_with_negative_feedback(state, product, weight=0.6)
                tokens, _ = extract_feature_tokens(product, category)
                disliked_tokens.update(tokens)
            state["disliked_ids"] = list(disliked_ids)
            state["disliked_tokens"] = list(disliked_tokens)

        selected_ids = await self._current_selection_sequence(db, game)
        used = set(selected_ids)
        previous_candidates = set(round_row.candidate_ids or [])
        disliked_ids = set(state.get("disliked_ids") or [])
        disliked_tokens = set(state.get("disliked_tokens") or [])
        all_products = await self._all_products_for_scoring(db, category)
        candidates_source = [
            p
            for p in all_products
            if str(p["_id"]) not in used and str(p["_id"]) not in previous_candidates and str(p["_id"]) not in disliked_ids
        ]
        if len(candidates_source) < 10:
            raise ValueError("Not enough products left to generate a round")

        scored = self._rank_candidates(model, state, candidates_source, category, disliked_tokens)
        candidate_ids = self._build_round_candidates(game_id, round_number, category, scored)
        candidate_products = await self._get_products_by_ids(
            db,
            candidate_ids,
            projection=self._card_projection(category),
        )
        pre_metrics = await self._metrics_for_state(db, model, state, selected_ids, category)

        round_row.candidate_ids = candidate_ids
        round_row.pre_metrics = pre_metrics
        round_row.completed = False

        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
        if game_row:
            game_row.status = "playing"
            game_row.model_state = state
            game_row.updated_at = datetime.utcnow()
        await db.commit()

        return {
            "round_number": round_number,
            "category": category,
            "category_copy": category_copy(category),
            "candidates": [self._product_card(p, category) for p in candidate_products],
            "pre_round_metrics": pre_metrics,
        }
