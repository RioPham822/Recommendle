"""Post-game analytics helpers: summary, status, leaderboard, and player history."""

from __future__ import annotations

from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import and_, func, select
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
from ..db import GameRecord, GameRoundRecord, record_to_dict


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
        is_redesigned = self._is_redesigned_game(game)
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

        state = self._ensure_redesign_state(game.get("model_state") or model.init_state())
        round_stats = []
        cumulative_ai = 0
        cumulative_human = 0
        running_streak = 0
        for rnd in rounds:
            preference_match = bool(rnd.ai_correct)
            ai_correct = preference_match
            cumulative_ai += int(rnd.ai_points or 0)
            cumulative_human += int(rnd.human_points or 0)
            post = rnd.post_metrics or {}
            running_streak = running_streak + 1 if preference_match else 0
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
                    "preference_match": preference_match,
                    "current_match_streak": running_streak,
                }
            )

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

        total = self._rounds_played(game) if is_redesigned else len(rounds)
        if total <= 0:
            total = len(rounds)
        correct = sum(1 for r in rounds if r.ai_correct)
        exact = sum(1 for r in rounds if r.ai_pick_id == r.human_pick_id)
        current_match_streak, longest_match_streak, match_streak_target = self._match_progress(game)
        total_matches = int(state.get("total_matches") or correct)
        return {
            "game_id": str(game["_id"]),
            "schema_version": int(game.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
            "player_name": game["player_name"],
            "category": category,
            "mode": game.get("mode") or "classic",
            "category_copy": category_copy(category),
            "total_rounds": total,
            "human_score": game["human_score"],
            "ai_score": game["ai_score"],
            "rounds_played": total,
            "total_matches": total_matches,
            "match_rate": (total_matches / total) if total else 0.0,
            "current_match_streak": current_match_streak,
            "longest_match_streak": longest_match_streak,
            "match_streak_target": match_streak_target,
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
        current_match_streak, longest_match_streak, match_streak_target = self._match_progress(game)
        active_round = await db.scalar(
            select(GameRoundRecord)
            .where(and_(GameRoundRecord.game_id == str(game["_id"]), GameRoundRecord.completed.is_(False)))
            .order_by(GameRoundRecord.round_number.asc())
            .limit(1)
        )
        return {
            "id": str(game["_id"]),
            "schema_version": int(game.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
            "player_name": game["player_name"],
            "category": category,
            "mode": game.get("mode") or "classic",
            "category_copy": category_copy(category),
            "status": game["status"],
            "current_round": int(game.get("current_round", 0)),
            "total_rounds": int(game.get("total_rounds", 10)),
            "human_score": int(game.get("human_score", 0)),
            "ai_score": int(game.get("ai_score", 0)),
            "preference_deck": await self._preference_deck(db, game),
            "current_match_streak": current_match_streak,
            "longest_match_streak": longest_match_streak,
            "match_streak_target": match_streak_target,
            "rounds_played": self._rounds_played(game),
            "onboarding_complete": 1 <= len(game.get("onboarding_selected_ids", [])) <= self.MAX_ONBOARDING_SELECTIONS,
            "onboarding_selected_count": len(game.get("onboarding_selected_ids", [])),
            "round_in_progress": active_round.round_number if active_round else None,
        }

    async def get_leaderboard(
        self,
        db: AsyncSession,
        limit: int = 10,
        category: str = "fountain_pens",
    ) -> list[dict[str, Any]]:
        """Return top players for a category using each player's best completed game."""
        normalized_category = normalize_category(category)
        games = (
            (
                await db.execute(
                    select(GameRecord)
                    .where(
                        and_(
                            GameRecord.status == "completed",
                            GameRecord.category == normalized_category,
                            GameRecord.schema_version >= self.REDESIGN_SCHEMA_VERSION,
                        )
                    )
                    .order_by(
                        GameRecord.current_round.asc(),
                        GameRecord.updated_at.asc(),
                    )
                )
            )
            .scalars()
            .all()
        )
        best_by_player: dict[str, dict[str, Any]] = {}
        for game_row in games:
            game = record_to_dict(game_row)
            player_name = str(game.get("player_name") or "").strip()
            if not player_name:
                continue
            state = self._ensure_redesign_state(game.get("model_state") or {})
            rounds_completed = self._rounds_played(game)
            total_matches = int(state.get("total_matches") or game.get("human_score") or 0)
            candidate = {
                "schema_version": int(game.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
                "player_name": player_name,
                "category": normalize_category(game["category"]),
                "human_score": int(game.get("human_score") or 0),
                "ai_score": int(game.get("ai_score") or 0),
                "score_difference": int((game.get("human_score") or 0) - (game.get("ai_score") or 0)),
                "rounds_completed": rounds_completed,
                "rounds_to_complete": rounds_completed,
                "longest_match_streak": int(state.get("longest_match_streak") or 0),
                "match_rate": (total_matches / rounds_completed) if rounds_completed else 0.0,
                "created_at": game["created_at"],
                "updated_at": game.get("updated_at"),
            }
            current = best_by_player.get(player_name)
            if current is None:
                best_by_player[player_name] = candidate
                continue
            candidate_key = (
                candidate["rounds_to_complete"],
                -candidate["match_rate"],
                -(candidate["longest_match_streak"] or 0),
                candidate["updated_at"] or candidate["created_at"],
            )
            current_key = (
                current["rounds_to_complete"],
                -current["match_rate"],
                -(current["longest_match_streak"] or 0),
                current["updated_at"] or current["created_at"],
            )
            if candidate_key < current_key:
                best_by_player[player_name] = candidate

        ranked_games = sorted(
            best_by_player.values(),
            key=lambda entry: (
                entry["rounds_to_complete"],
                -entry["match_rate"],
                -(entry["longest_match_streak"] or 0),
                entry["updated_at"] or entry["created_at"],
            ),
        )[: int(limit)]

        entries: list[dict[str, Any]] = []
        for index, game in enumerate(ranked_games):
            entries.append(
                {
                    "rank": index + 1,
                    "schema_version": int(game.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
                    "player_name": game["player_name"],
                    "category": normalize_category(game["category"]),
                    "human_score": int(game.get("human_score") or 0),
                    "ai_score": int(game.get("ai_score") or 0),
                    "score_difference": int((game.get("human_score") or 0) - (game.get("ai_score") or 0)),
                    "rounds_completed": int(game.get("rounds_completed") or 0),
                    "rounds_to_complete": int(game.get("rounds_to_complete") or 0),
                    "longest_match_streak": int(game.get("longest_match_streak") or 0),
                    "match_rate": float(game.get("match_rate") or 0.0),
                    "created_at": game["created_at"],
                }
            )
        return entries

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
        for game_row in games:
            game = record_to_dict(game_row)
            is_redesigned = self._is_redesigned_game(game)
            total = self._rounds_played(game) if is_redesigned else int(game_row.current_round or 0)
            h = int(game_row.human_score or 0)
            a = int(game_row.ai_score or 0)
            state = self._ensure_redesign_state(game.get("model_state") or {})
            ai_correct = int(state.get("total_matches") or 0)
            if not is_redesigned:
                ai_correct = int(
                    await db.scalar(
                        select(func.count())
                        .select_from(GameRoundRecord)
                        .where(
                            and_(
                                GameRoundRecord.game_id == game_row.id,
                                GameRoundRecord.completed.is_(True),
                                GameRoundRecord.ai_correct.is_(True),
                            )
                        )
                    )
                    or 0
                )
            results.append(
                {
                    "game_id": game_row.id,
                    "schema_version": int(game.get("schema_version") or self.LEGACY_SCHEMA_VERSION),
                    "player_name": player_name,
                    "category": normalize_category(game_row.category),
                    "human_score": h,
                    "ai_score": a,
                    "score_difference": h - a,
                    "rounds_played": total,
                    "ai_accuracy": (int(ai_correct or 0) / total) if total else 0,
                    "rounds_to_complete": total if is_redesigned else 0,
                    "longest_match_streak": int(state.get("longest_match_streak") or 0) if is_redesigned else 0,
                    "match_rate": (int(state.get("total_matches") or 0) / total) if is_redesigned and total else 0.0,
                    "created_at": game_row.created_at,
                }
            )
        return results
