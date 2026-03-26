"""Post-game analytics helpers: summary, status, leaderboard, and player history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, desc, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..category_profiles import (
    category_copy,
    get_category_profile,
)
from ..category_profiles import humanize_feature_list as profile_humanize_feature_list
from ..category_profiles import (
    normalize_category,
    numeric_preference_label,
)
from ..db import GameRecord, GameRoundRecord


def humanize_feature_list(raw_list: list[tuple[str, float]]) -> list[tuple[str, float]]:
    """Convert raw feature tokens into user-facing labels."""
    return profile_humanize_feature_list(raw_list)


class GameInsightsMixin:
    """Composable read/query operations for completed and in-progress games."""

    async def get_game_summary(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        """Return final game analytics, recommendations, and hidden-preference insights."""
        game = await self._get_game(db, game_id)
        model = await self._ensure_model(db)
        category = self._game_category(game)
        profile = get_category_profile(category)
        if game.get("status") != "completed":
            raise ValueError("Game is not yet completed")

        rounds = (
            (
                await db.execute(
                    select(GameRoundRecord)
                    .where(and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.completed.is_(True)))
                    .order_by(GameRoundRecord.round_number.asc())
                )
            )
            .scalars()
            .all()
        )

        round_stats = []
        cumulative_ai = 0
        cumulative_human = 0
        for rnd in rounds:
            ai_correct = bool(rnd.ai_correct)
            cumulative_ai += int(rnd.ai_points or 0)
            cumulative_human += int(rnd.human_points or 0)
            post = rnd.post_metrics or {}
            round_stats.append(
                {
                    "round_number": rnd.round_number,
                    "ai_correct": ai_correct,
                    "ai_rank_of_pick": rnd.ai_rank_of_pick,
                    "ai_confidence": rnd.ai_confidence or 0,
                    "coherence": post.get("coherence_score", 0),
                    "predicted_rating": post.get("predicted_prefix_rating", 3.0),
                    "cumulative_ai": cumulative_ai,
                    "cumulative_human": cumulative_human,
                }
            )

        state = game.get("model_state") or model.init_state()
        if self._align_state_to_feature_space(model, state):
            game_row = await db.scalar(select(GameRecord).where(GameRecord.id == str(game["_id"])))
            if game_row:
                game_row.model_state = state
                game_row.updated_at = datetime.utcnow()
                await db.commit()

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

        all_products = await self._all_products_for_scoring(db, category)
        disliked_tokens = set(state.get("disliked_tokens") or [])
        selected_ids = set(await self._current_selection_sequence(db, game))
        disliked_ids = set(state.get("disliked_ids") or [])
        filtered_products = [
            p for p in all_products if str(p.get("_id")) not in selected_ids and str(p.get("_id")) not in disliked_ids
        ]
        scored = self._rank_candidates(model, state, filtered_products, category, disliked_tokens)
        top5_recs = []
        for score, product in scored[:5]:
            card = self._product_card(product, category)
            card["score"] = float(score)
            top5_recs.append(card)
        top5_ids = {r["id"] for r in top5_recs}

        all_selected_ids = await self._current_selection_sequence(db, game)
        all_selected_products = await self._get_products_by_ids(
            db,
            all_selected_ids,
            projection=self._feature_projection(category),
        )
        hidden_raw = model.detect_hidden_preferences(state, all_selected_products)
        hidden_prefs = humanize_feature_list([(h["feature"], round(h["latency"], 3)) for h in hidden_raw])
        learned_names = {name.lower() for name, _ in learned_likes}
        hidden_prefs = [(n, w) for n, w in hidden_prefs if n.lower() not in learned_names]

        hidden_gem_results = model.get_hidden_gem_products(state, all_selected_products, all_products, top_n=10)
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

        hidden_gems_explanation = ""
        if hidden_prefs:
            feature_names = [name for name, _ in hidden_prefs[:3]]
            if len(feature_names) == 1:
                hidden_gems_explanation = (
                    f'Although you may not have noticed, your choices reveal a hidden affinity for "{feature_names[0]}". '
                    f"The {profile.item_plural} below match this latent pattern the AI discovered in your selections."
                )
            else:
                joined = ", ".join(f'"{n}"' for n in feature_names[:-1]) + f' and "{feature_names[-1]}"'
                hidden_gems_explanation = (
                    f"Your choices reveal hidden patterns the AI detected: {joined}. "
                    f"These features appeared across your selections even though you likely were not targeting them. "
                    f"The {profile.item_plural} below match these latent preferences."
                )

        total = len(rounds)
        correct = sum(1 for r in rounds if r.ai_correct)
        exact = sum(1 for r in rounds if r.ai_pick_id == r.human_pick_id)
        return {
            "game_id": str(game["_id"]),
            "player_name": game["player_name"],
            "category": category,
            "mode": game.get("mode") or "classic",
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

    async def get_game_status(self, db: AsyncSession, game_id: str) -> dict[str, Any]:
        """Return current game progress and scoreboard state."""
        game = await self._get_game(db, game_id)
        category = self._game_category(game)
        active_round = await db.scalar(
            select(GameRoundRecord)
            .where(and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.completed.is_(False)))
            .order_by(GameRoundRecord.round_number.asc())
            .limit(1)
        )
        return {
            "id": str(game["_id"]),
            "player_name": game["player_name"],
            "category": category,
            "mode": game.get("mode") or "classic",
            "category_copy": category_copy(category),
            "status": game["status"],
            "current_round": int(game.get("current_round", 0)),
            "total_rounds": int(game.get("total_rounds", 10)),
            "human_score": int(game.get("human_score", 0)),
            "ai_score": int(game.get("ai_score", 0)),
            "onboarding_complete": len(game.get("onboarding_selected_ids", [])) == 10,
            "onboarding_selected_count": len(game.get("onboarding_selected_ids", [])),
            "round_in_progress": active_round.round_number if active_round else None,
        }

    async def get_leaderboard(
        self,
        db: AsyncSession,
        limit: int = 10,
        category: str = "fountain_pens",
    ) -> list[dict[str, Any]]:
        """Return top completed games for a category sorted by performance."""
        normalized_category = normalize_category(category)
        games = (
            (
                await db.execute(
                    select(GameRecord)
                    .where(and_(GameRecord.status == "completed", GameRecord.category == normalized_category))
                    .order_by(
                        desc(GameRecord.human_score - GameRecord.ai_score),
                        desc(GameRecord.human_score),
                        GameRecord.created_at.asc(),
                    )
                    .limit(int(limit))
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "rank": index + 1,
                "player_name": game.player_name,
                "category": normalize_category(game.category),
                "human_score": int(game.human_score),
                "ai_score": int(game.ai_score),
                "score_difference": int(game.human_score - game.ai_score),
                "rounds_completed": int(game.current_round or 0),
                "created_at": game.created_at,
            }
            for index, game in enumerate(games)
        ]

    async def get_player_history(
        self,
        db: AsyncSession,
        player_name: str,
        limit: int = 20,
        category: str = "fountain_pens",
    ) -> list[dict[str, Any]]:
        """Return completed game history for one player in a category."""
        normalized_category = normalize_category(category)
        games = (
            (
                await db.execute(
                    select(GameRecord)
                    .where(
                        and_(
                            GameRecord.player_name == player_name,
                            GameRecord.status == "completed",
                            GameRecord.category == normalized_category,
                        )
                    )
                    .order_by(GameRecord.created_at.desc())
                    .limit(limit)
                )
            )
            .scalars()
            .all()
        )

        results: list[dict[str, Any]] = []
        for game in games:
            total = int(game.current_round or 0)
            h = int(game.human_score or 0)
            a = int(game.ai_score or 0)
            ai_correct = await db.scalar(
                select(func.count())
                .select_from(GameRoundRecord)
                .where(
                    and_(
                        GameRoundRecord.game_id == game.id,
                        GameRoundRecord.completed.is_(True),
                        GameRoundRecord.ai_correct.is_(True),
                    )
                )
            )
            results.append(
                {
                    "game_id": game.id,
                    "player_name": player_name,
                    "category": normalize_category(game.category),
                    "human_score": h,
                    "ai_score": a,
                    "score_difference": h - a,
                    "rounds_played": total,
                    "ai_accuracy": (int(ai_correct or 0) / total) if total else 0,
                    "created_at": game.created_at,
                }
            )
        return results
