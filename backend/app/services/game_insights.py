from __future__ import annotations
"""Post-game analytics and leaderboard/history methods."""

from datetime import datetime
from typing import Any

import numpy as np
from motor.motor_asyncio import AsyncIOMotorDatabase

from ..category_profiles import (
    category_copy,
    get_category_profile,
    humanize_feature_list as profile_humanize_feature_list,
    normalize_category,
    numeric_preference_label,
)


def humanize_feature_list(raw_list: list[tuple[str, float]]) -> list[tuple[str, float]]:
    return profile_humanize_feature_list(raw_list)


class GameInsightsMixin:
    """Summary, status, and leaderboard methods extracted from `game_service.py`."""

    async def get_game_summary(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
    ) -> dict[str, Any]:
        """Return post-game insights: round-by-round stats, learned profile, top-5 recs."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)
        profile = get_category_profile(category)

        if game.get("status") != "completed":
            raise ValueError("Game is not yet completed")

        # Load all rounds
        cursor = db.game_rounds.find(
            {"game_id": game["_id"], "completed": True}
        ).sort("round_number", 1)
        rounds = await cursor.to_list(length=None)

        # Round-by-round data for charts
        round_stats = []
        cumulative_ai = 0
        cumulative_human = 0
        for rnd in rounds:
            ai_correct = rnd.get("ai_correct", False)
            cumulative_ai += rnd.get("ai_points", 0)
            cumulative_human += rnd.get("human_points", 0)
            post = rnd.get("post_metrics", {})
            round_stats.append({
                "round_number": rnd["round_number"],
                "ai_correct": ai_correct,
                "ai_rank_of_pick": rnd.get("ai_rank_of_pick", None),
                "ai_confidence": rnd.get("ai_confidence", 0),
                "coherence": post.get("coherence_score", 0),
                "predicted_rating": post.get("predicted_prefix_rating", 3.0),
                "cumulative_ai": cumulative_ai,
                "cumulative_human": cumulative_human,
            })

        # Model's learned preferences from the final state
        state = game.get("model_state") or model.init_state()
        if self._align_state_to_feature_space(model, state):
            await db.games.update_one(
                {"_id": game["_id"]},
                {"$set": {"model_state": state, "updated_at": datetime.utcnow()}},
            )
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

        learned_likes = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w > 0][:10])
        learned_dislikes = humanize_feature_list([(n, round(w, 3)) for n, w in feature_weights if w < 0][:5])

        # Top-5 recommended products from the full catalog
        all_products = await self._all_products_for_scoring(db, category)
        scored = self._rank_candidates(model, state, all_products)
        top5_recs = []
        for score, product in scored[:5]:
            card = self._product_card(product, category)
            card["score"] = float(score)
            top5_recs.append(card)
        top5_ids = {r["id"] for r in top5_recs}

        # -- Hidden preference discovery (final) -----------------
        all_selected_ids = await self._current_selection_sequence(db, game)
        all_selected_products = await self._get_products_by_ids(
            db,
            all_selected_ids,
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
        hidden_raw = model.detect_hidden_preferences(state, all_selected_products)
        hidden_prefs = humanize_feature_list(
            [(h["feature"], round(h["latency"], 3)) for h in hidden_raw]
        )

        # Remove hidden prefs that already appear in learned_likes
        learned_names = {name.lower() for name, _ in learned_likes}
        hidden_prefs = [
            (n, w) for n, w in hidden_prefs
            if n.lower() not in learned_names
        ]

        # Hidden gem products -- products the user did not see but match latent tastes.
        hidden_gem_results = model.get_hidden_gem_products(
            state, all_selected_products, all_products, top_n=10
        )
        hidden_gems_cards = []
        for gem_score, gem_product, matched_features in hidden_gem_results:
            pid = str(gem_product["_id"])
            if pid in top5_ids:
                continue
            card = self._product_card(gem_product, category)
            card["score"] = round(float(gem_score), 3)
            hidden_gems_cards.append(card)
            if len(hidden_gems_cards) >= 5:
                break

        # Build narrative explanation
        hidden_gems_explanation = ""
        if hidden_prefs:
            feature_names = [name for name, _ in hidden_prefs[:3]]
            if len(feature_names) == 1:
                hidden_gems_explanation = (
                    f"Although you may not have noticed, your choices reveal a hidden "
                    f"affinity for \"{feature_names[0]}\". The {profile.item_plural} below match this "
                    f"latent pattern the AI discovered in your selections."
                )
            else:
                joined = ", ".join(f'\"{n}\"' for n in feature_names[:-1])
                joined += f' and \"{feature_names[-1]}\"'
                hidden_gems_explanation = (
                    f"Your choices reveal hidden patterns the AI detected: {joined}. "
                    f"These features appeared across your selections even though you "
                    f"likely weren't targeting them. The {profile.item_plural} below match these "
                    f"latent preferences."
                )

        # Accuracy summary
        total = len(rounds)
        correct = sum(1 for r in rounds if r.get("ai_correct"))
        exact = sum(1 for r in rounds if r.get("ai_pick_id") == r.get("human_pick_id"))

        return {
            "game_id": str(game["_id"]),
            "player_name": game["player_name"],
            "category": category,
            "category_copy": category_copy(category),
            "total_rounds": total,
            "human_score": game["human_score"],
            "ai_score": game["ai_score"],
            "accuracy": {
                "top3_correct": correct,
                "exact_correct": exact,
                "top3_rate": correct / total if total else 0,
                "exact_rate": exact / total if total else 0,
            },
            "round_stats": round_stats,
            "learned_preferences": learned_likes,
            "learned_dislikes": learned_dislikes,
            "top5_recommendations": top5_recs,
            "hidden_preferences": hidden_prefs,
            "hidden_gems_products": hidden_gems_cards,
            "hidden_gems_explanation": hidden_gems_explanation,
        }

    async def get_game_status(
        self,
        db: AsyncIOMotorDatabase,
        game_id: str,
    ) -> dict[str, Any]:
        """Return lightweight game progress/status for polling and resume flows."""
        game = await self._get_game(db, game_id)
        category = self._game_category(game)

        active_round = await db.game_rounds.find_one(
            {"game_id": game["_id"], "completed": False},
            {"round_number": 1},
            sort=[("round_number", 1)],
        )

        return {
            "id": str(game["_id"]),
            "player_name": game["player_name"],
            "category": category,
            "category_copy": category_copy(category),
            "status": game["status"],
            "current_round": int(game.get("current_round", 0)),
            "total_rounds": int(game.get("total_rounds", 10)),
            "human_score": int(game.get("human_score", 0)),
            "ai_score": int(game.get("ai_score", 0)),
            "onboarding_complete": len(game.get("onboarding_selected_ids", [])) == 10,
            "onboarding_selected_count": len(game.get("onboarding_selected_ids", [])),
            "round_in_progress": active_round.get("round_number") if active_round else None,
        }

    async def get_leaderboard(
        self,
        db: AsyncIOMotorDatabase,
        limit: int = 10,
        category: str = "fountain_pens",
    ) -> list[dict[str, Any]]:
        """Return top completed games for a category sorted by score delta."""
        normalized_category = normalize_category(category)
        pipeline = [
            {"$match": {"status": "completed", **self._category_query(normalized_category)}},
            {"$addFields": {"score_difference": {"$subtract": ["$human_score", "$ai_score"]}}},
            {"$sort": {"score_difference": -1, "human_score": -1, "created_at": 1}},
            {"$limit": int(limit)},
        ]
        games = await db.games.aggregate(pipeline).to_list(length=limit)

        return [
            {
                "rank": index + 1,
                "player_name": game["player_name"],
                "category": self._game_category(game),
                "human_score": int(game["human_score"]),
                "ai_score": int(game["ai_score"]),
                "score_difference": int(game["human_score"] - game["ai_score"]),
                "rounds_completed": int(game.get("current_round", 0)),
                "created_at": game["created_at"],
            }
            for index, game in enumerate(games)
        ]

    async def get_player_history(
        self,
        db: AsyncIOMotorDatabase,
        player_name: str,
        limit: int = 20,
        category: str = "fountain_pens",
    ) -> list[dict[str, Any]]:
        """Return completed games for a given player, most recent first."""
        normalized_category = normalize_category(category)
        cursor = db.games.find(
            {"player_name": player_name, "status": "completed", **self._category_query(normalized_category)},
        ).sort("created_at", -1).limit(limit)
        games = await cursor.to_list(length=limit)

        results: list[dict[str, Any]] = []
        for game in games:
            game_id = str(game["_id"])
            total = int(game.get("current_round", 0))
            h = int(game.get("human_score", 0))
            a = int(game.get("ai_score", 0))

            # Count AI correct rounds
            ai_correct = await db.game_rounds.count_documents(
                {"game_id": game["_id"], "completed": True, "ai_correct": True}
            )

            results.append({
                "game_id": game_id,
                "player_name": player_name,
                "category": self._game_category(game),
                "human_score": h,
                "ai_score": a,
                "score_difference": h - a,
                "rounds_played": total,
                "ai_accuracy": ai_correct / total if total else 0,
                "created_at": game["created_at"],
            })

        return results
