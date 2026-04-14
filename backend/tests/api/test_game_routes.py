import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.routes import game
from app.routes.game import (
    get_categories,
    get_game_status,
    get_game_summary,
    get_leaderboard,
    get_onboarding,
    get_player_history,
    get_resume_state,
    refresh_onboarding,
    refresh_round,
    start_game,
    start_round,
    submit_feedback,
    submit_onboarding,
    submit_round_pick,
    submit_seed_preferences,
    update_preferences,
)
from app.schemas_game import (
    FeedbackSubmit,
    GameCreate,
    OnboardingRefreshSubmit,
    OnboardingSubmit,
    PreferenceUpdateSubmit,
    RoundPickSubmit,
    RoundRefreshSubmit,
    SeedPreferencesSubmit,
)


def _product_card(product_id: str, title: str = "Item"):
    return {
        "id": product_id,
        "category": "movies",
        "title": title,
        "vendor": "Studio",
        "attributes": {},
        "meta_badges": [],
        "tags": [],
        "predicted_match_features": [],
    }


class GameRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_categories_returns_service_data(self):
        categories = [
            {
                "id": "movies",
                "display_name": "Movies",
                "item_singular": "movie",
                "item_plural": "movies",
                "available_count": 10,
            }
        ]
        with patch.object(game.game_service, "get_categories", AsyncMock(return_value=categories)) as mocked:
            result = await get_categories(db=object())

        mocked.assert_awaited_once()
        self.assertEqual(result[0]["id"], "movies")

    async def test_get_leaderboard_maps_value_error_to_http_400(self):
        rows = [
            {
                "rank": 1,
                "player_name": "Alice",
                "category": "movies",
                "human_score": 4,
                "ai_score": 2,
                "score_difference": 2,
                "rounds_completed": 5,
                "created_at": datetime(2026, 1, 1, 12, 0, 0),
            }
        ]
        with patch.object(game.game_service, "get_leaderboard", AsyncMock(return_value=rows)) as mocked:
            result = await get_leaderboard(limit=5, category="movies", db=object())
        mocked.assert_awaited_once()
        self.assertEqual(result[0]["player_name"], "Alice")

        with patch.object(game.game_service, "get_leaderboard", AsyncMock(side_effect=ValueError("bad category"))):
            with self.assertRaises(HTTPException) as exc:
                await get_leaderboard(limit=5, category="bad", db=object())
        self.assertEqual(exc.exception.status_code, 400)

    async def test_get_player_history_returns_rows(self):
        rows = [
            {
                "game_id": "g1",
                "player_name": "Alice",
                "category": "movies",
                "human_score": 5,
                "ai_score": 3,
                "score_difference": 2,
                "rounds_played": 5,
                "ai_accuracy": 0.6,
                "created_at": datetime(2026, 1, 1, 12, 0, 0),
            }
        ]
        with patch.object(game.game_service, "get_player_history", AsyncMock(return_value=rows)) as mocked:
            result = await get_player_history("Alice", limit=5, category="movies", db=object())

        mocked.assert_awaited_once()
        self.assertEqual(result[0]["game_id"], "g1")

    async def test_start_game_uses_current_user_display_name_when_present(self):
        payload = GameCreate(player_name="Guest", category="movies", mode="classic", fresh_start=True)
        result_payload = {
            "id": "g1",
            "player_name": "Alice",
            "category": "movies",
            "mode": "classic",
            "status": "onboarding",
            "total_rounds": 5,
            "human_score": 0,
            "ai_score": 0,
            "created_at": datetime(2026, 1, 1, 12, 0, 0),
            "resumed": False,
        }
        current_user = SimpleNamespace(display_name="Alice")

        with patch.object(game.game_service, "create_game", AsyncMock(return_value=result_payload)) as mocked:
            result = await start_game(payload, db=object(), current_user=current_user)

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.kwargs["player_name"], "Alice")
        self.assertEqual(result.id, "g1")

    async def test_start_game_maps_value_error_to_http_400(self):
        payload = GameCreate(player_name="Guest", category="movies", mode="classic", fresh_start=False)
        with patch.object(game.game_service, "create_game", AsyncMock(side_effect=ValueError("bad game"))):
            with self.assertRaises(HTTPException) as exc:
                await start_game(payload, db=object(), current_user=None)

        self.assertEqual(exc.exception.status_code, 400)

    async def test_get_resume_state_uses_current_user_name(self):
        service_result = {
            "exists": True,
            "can_start_fresh": True,
            "game_id": "g1",
            "player_name": "Alice",
            "category": "movies",
            "status": "ready",
            "current_round": 1,
            "total_rounds": 5,
        }
        current_user = SimpleNamespace(display_name="Alice")

        with patch.object(game.game_service, "get_resume_state", AsyncMock(return_value=service_result)) as mocked:
            result = await get_resume_state("Guest", category="movies", db=object(), current_user=current_user)

        mocked.assert_awaited_once()
        self.assertEqual(mocked.await_args.kwargs["player_name"], "Alice")
        self.assertTrue(result.exists)

    async def test_get_onboarding_and_refresh_onboarding(self):
        onboarding_result = {
            "game_id": "g1",
            "category": "movies",
            "pool_size": 2,
            "category_copy": {},
            "display_schema": {},
            "preference_deck": [],
            "products": [_product_card("p1", "Arrival"), _product_card("p2", "Heat")],
        }
        refresh_payload = OnboardingRefreshSubmit(selected_product_ids=["p1"])

        with patch.object(game.game_service, "get_onboarding", AsyncMock(return_value=onboarding_result)) as get_mock, patch.object(
            game.game_service,
            "refresh_onboarding",
            AsyncMock(return_value=onboarding_result),
        ) as refresh_mock:
            onboarding = await get_onboarding("g1", db=object())
            refreshed = await refresh_onboarding("g1", refresh_payload, db=object())

        get_mock.assert_awaited_once()
        refresh_mock.assert_awaited_once()
        self.assertEqual(onboarding.products[0].id, "p1")
        self.assertEqual(refreshed.pool_size, 2)

    async def test_submit_onboarding_returns_validated_payload(self):
        payload = OnboardingSubmit(selected_product_ids=["p1"], rating=4)
        result_payload = {
            "accepted": True,
            "coherence_score": 0.8,
            "predicted_prefix_rating": 4.2,
            "next_round": 1,
        }
        with patch.object(game.game_service, "submit_onboarding", AsyncMock(return_value=result_payload)) as mocked:
            result = await submit_onboarding("g1", payload, db=object())

        mocked.assert_awaited_once()
        self.assertTrue(result.accepted)

    async def test_start_round_and_refresh_round(self):
        round_payload = {
            "round_number": 1,
            "category": "movies",
            "round_mode": "classic",
            "category_copy": {},
            "display_schema": {},
            "preference_deck": [],
            "candidates": [_product_card("p1", "Arrival"), _product_card("p2", "Heat")],
            "pre_round_metrics": {"coherence_score": 0.4, "predicted_prefix_rating": 3.5},
        }
        refresh_payload = RoundRefreshSubmit(less_like_ids=["p2"])

        with patch.object(game.game_service, "start_round", AsyncMock(return_value=round_payload)) as start_mock, patch.object(
            game.game_service,
            "refresh_round",
            AsyncMock(return_value=round_payload),
        ) as refresh_mock:
            started = await start_round("g1", db=object())
            refreshed = await refresh_round("g1", refresh_payload, db=object())

        start_mock.assert_awaited_once()
        refresh_mock.assert_awaited_once()
        self.assertEqual(started.round_number, 1)
        self.assertEqual(refreshed.candidates[1].id, "p2")

    async def test_submit_round_pick_feedback_seed_and_preferences(self):
        pick_payload = RoundPickSubmit(product_id="p1", less_like_ids=["p2"])
        feedback_payload = FeedbackSubmit(product_id="p2", action="less_like_this")
        seed_payload = SeedPreferencesSubmit(
            likes={"genres": ["Sci-Fi"]},
            dislikes={"genres": ["Horror"]},
            like_product_ids=["p1"],
            dislike_product_ids=["p3"],
        )
        preference_payload = PreferenceUpdateSubmit(active_preference_ids=["pref-1"])

        round_result = {
            "round_number": 1,
            "category": "movies",
            "round_mode": "classic",
            "category_copy": {},
            "preference_deck": [],
            "human_pick": _product_card("p1", "Arrival"),
            "ai_pick": {**_product_card("p2", "Heat"), "score": 0.81},
            "ai_correct": True,
            "human_points": 1,
            "ai_points": 0,
            "total_human_score": 1,
            "total_ai_score": 0,
            "ai_explanation": {"reason": "closest match", "top_candidates": [{**_product_card("p2", "Heat"), "score": 0.81}]},
            "post_round_metrics": {"coherence_score": 0.7, "predicted_prefix_rating": 4.1},
            "game_complete": False,
        }
        feedback_result = {"accepted": True, "action": "less_like_this", "product_id": "p2"}
        seed_result = {"accepted": True}
        preference_result = {
            "game_id": "g1",
            "category": "movies",
            "category_copy": {},
            "display_schema": {},
            "preference_deck": [],
            "round": {
                "round_number": 2,
                "category": "movies",
                "round_mode": "classic",
                "category_copy": {},
                "display_schema": {},
                "preference_deck": [],
                "candidates": [_product_card("p3", "Memento")],
                "pre_round_metrics": {"coherence_score": 0.5, "predicted_prefix_rating": 3.8},
            },
        }

        with patch.object(game.game_service, "submit_pick", AsyncMock(return_value=round_result)) as pick_mock, patch.object(
            game.game_service,
            "submit_feedback",
            AsyncMock(return_value=feedback_result),
        ) as feedback_mock, patch.object(
            game.game_service,
            "submit_seed_preferences",
            AsyncMock(return_value=seed_result),
        ) as seed_mock, patch.object(
            game.game_service,
            "update_preferences",
            AsyncMock(return_value=preference_result),
        ) as pref_mock:
            picked = await submit_round_pick("g1", 1, pick_payload, db=object())
            feedback = await submit_feedback("g1", feedback_payload, db=object())
            seeded = await submit_seed_preferences("g1", seed_payload, db=object())
            updated = await update_preferences("g1", preference_payload, db=object())

        pick_mock.assert_awaited_once()
        feedback_mock.assert_awaited_once()
        seed_mock.assert_awaited_once()
        pref_mock.assert_awaited_once()
        self.assertTrue(picked.ai_correct)
        self.assertEqual(feedback.product_id, "p2")
        self.assertTrue(seeded.accepted)
        self.assertEqual(updated.round.round_number, 2)

    async def test_get_game_status_and_summary_translate_error_codes(self):
        status_payload = {
            "id": "g1",
            "player_name": "Alice",
            "category": "movies",
            "mode": "classic",
            "category_copy": {},
            "status": "playing",
            "current_round": 1,
            "total_rounds": 5,
            "human_score": 1,
            "ai_score": 0,
            "preference_deck": [],
            "onboarding_complete": True,
            "onboarding_selected_count": 3,
        }
        summary_payload = {
            "game_id": "g1",
            "player_name": "Alice",
            "category": "movies",
            "mode": "classic",
            "category_copy": {},
            "total_rounds": 5,
            "human_score": 4,
            "ai_score": 1,
            "accuracy": {"top3_correct": 4, "exact_correct": 2, "top3_rate": 0.8, "exact_rate": 0.4},
            "round_stats": [],
            "top5_recommendations": [{**_product_card("p1", "Arrival"), "score": 0.9}],
        }
        with patch.object(game.game_service, "get_game_status", AsyncMock(return_value=status_payload)) as status_mock, patch.object(
            game.game_service,
            "get_game_summary",
            AsyncMock(return_value=summary_payload),
        ) as summary_mock:
            status = await get_game_status("g1", db=object())
            summary = await get_game_summary("g1", db=object())

        status_mock.assert_awaited_once()
        summary_mock.assert_awaited_once()
        self.assertEqual(status.status, "playing")
        self.assertEqual(summary.game_id, "g1")

        with patch.object(game.game_service, "get_game_status", AsyncMock(side_effect=ValueError("missing"))):
            with self.assertRaises(HTTPException) as status_exc:
                await get_game_status("missing", db=object())
        self.assertEqual(status_exc.exception.status_code, 404)

        with patch.object(game.game_service, "get_game_summary", AsyncMock(side_effect=ValueError("not done"))):
            with self.assertRaises(HTTPException) as summary_exc:
                await get_game_summary("g1", db=object())
        self.assertEqual(summary_exc.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
