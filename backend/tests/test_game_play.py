import unittest
from unittest.mock import patch

from app.services.game_play import GamePlayMixin, humanize_feature, humanize_feature_list


class _FakeModel:
    def init_state(self):
        return {"user_vec": [], "seeded": False}

    def update_with_negative_feedback(self, state, product, weight=0.6):
        return None


class _FakeRoundRow:
    def __init__(self, candidate_ids=None, completed=False):
        self.candidate_ids = candidate_ids or []
        self.completed = completed
        self.pre_metrics = None


class _FakeService(GamePlayMixin):
    DEFAULT_MATCH_STREAK_TARGET = 3
    REDESIGN_SCHEMA_VERSION = 3

    def __init__(self):
        self._products = []
        self._pool_result = []
        self._seeded_result = []
        self._refresh_game = None

    async def _all_products_for_onboarding_sample(self, db, category):
        return list(self._products)

    def _diverse_onboarding_sample(self, candidate_products, game_id, category):
        return list(self._pool_result)

    def _seeded_onboarding_sample(self, candidate_products, game_id, category, model, state):
        return list(self._seeded_result or self._pool_result)

    async def _ensure_model(self, db):
        return _FakeModel()

    def _ensure_redesign_state(self, state):
        return dict(state or {"user_vec": [], "seeded": False})

    def _align_state_to_feature_space(self, model, state):
        return None

    async def _get_game(self, db, game_id):
        return dict(self._refresh_game)

    def _game_category(self, game):
        return game.get("category", "fountain_pens")


class GamePlayHelperTests(unittest.TestCase):
    def test_humanize_feature_delegates_to_profile_helper(self):
        with patch("app.services.game_play.profile_humanize_feature", return_value="Nice Label") as mock_helper:
            result = humanize_feature("raw_token")

        self.assertEqual(result, "Nice Label")
        mock_helper.assert_called_once_with("raw_token")

    def test_humanize_feature_list_delegates_to_profile_helper(self):
        raw = [("feature_a", 0.8)]
        expected = [("Feature A", 0.8)]
        with patch("app.services.game_play.profile_humanize_feature_list", return_value=expected) as mock_helper:
            result = humanize_feature_list(raw)

        self.assertEqual(result, expected)
        mock_helper.assert_called_once_with(raw)


class GamePlayMixinTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_onboarding_pool_rejects_too_many_preserved_ids(self):
        service = _FakeService()

        with self.assertRaisesRegex(ValueError, "at most 10 onboarding selections"):
            await service._build_onboarding_pool(
                None,
                {"_id": "game-1", "onboarding_pool_ids": []},
                "fountain_pens",
                preserved_ids=[f"id-{i}" for i in range(11)],
            )

    async def test_build_onboarding_pool_returns_existing_pool_when_preserved_ids_are_present(self):
        service = _FakeService()
        game = {
            "_id": "game-1",
            "onboarding_pool_ids": ["a", "b", "c"],
        }

        result = await service._build_onboarding_pool(
            None,
            game,
            "fountain_pens",
            preserved_ids=["a", "c"],
        )

        self.assertEqual(result, ["a", "b", "c"])

    async def test_build_onboarding_pool_rejects_missing_preserved_product(self):
        service = _FakeService()
        service._products = [
            {"_id": "p1"},
            {"_id": "p2"},
        ]
        service._pool_result = ["p1", "p2"]

        with self.assertRaisesRegex(ValueError, "no longer available"):
            await service._build_onboarding_pool(
                None,
                {"_id": "game-1", "onboarding_pool_ids": []},
                "fountain_pens",
                preserved_ids=["missing-id"],
                force_refresh=True,
            )

    async def test_start_round_rejects_incomplete_onboarding(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "model_state": {},
            "onboarding_selected_ids": [],
            "status": "onboarding",
            "current_round": 0,
        }

        with self.assertRaisesRegex(ValueError, "Onboarding is incomplete"):
            await service.start_round(None, "game-1")

    async def test_refresh_round_rejects_when_round_is_not_active(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "model_state": {},
            "onboarding_selected_ids": ["p1"],
            "status": "playing",
            "current_round": 0,
        }

        class _FakeDB:
            async def scalar(self, stmt):
                return None

        with self.assertRaisesRegex(ValueError, "Round is not active"):
            await service.refresh_round(_FakeDB(), "game-1")
