import unittest
from types import SimpleNamespace
from unittest.mock import patch

import numpy as np

from app.services.game_play import GamePlayMixin, humanize_feature, humanize_feature_list


class _FakeModel:
    def init_state(self):
        return {"user_vec": [], "seeded": False}

    def update_with_negative_feedback(self, state, product, weight=0.6):
        state.setdefault("negative_ids", []).append(str(product.get("_id")))
        return None

    def update_with_selection(self, state, product, is_exception=False):
        state.setdefault("selected_ids", []).append(str(product.get("_id")))

    def update_with_prefix_rating(self, state, rating):
        state["last_rating"] = rating

    def detect_hidden_preferences(self, state, products):
        return [{"feature": "material", "latency": 0.61}]


class _FakeRoundRow:
    def __init__(self, candidate_ids=None, completed=False):
        self.candidate_ids = candidate_ids or []
        self.completed = completed
        self.pre_metrics = None


class _FakeDB:
    def __init__(self, scalar_results=None):
        self.scalar_results = list(scalar_results or [])
        self.added = []
        self.commits = 0

    async def scalar(self, stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1


class _FakeService(GamePlayMixin):
    DEFAULT_MATCH_STREAK_TARGET = 3
    REDESIGN_SCHEMA_VERSION = 3

    def __init__(self):
        self._products = []
        self._pool_result = []
        self._seeded_result = []
        self._refresh_game = None
        self._products_by_id = {}
        self._preference_deck_result = [{"id": "pref-1"}]
        self._all_scoring_products = []
        self._ranked_candidates = []

        self.recommender = type(
            "R",
            (),
            {
                "item_vectors": {},
                "item_norms": {},
                "feature_space": type(
                    "FS",
                    (),
                    {
                        "feature_index": {},
                        "vectorize": lambda self, product: np.array([1.0], dtype=np.float32),
                    },
                )(),
            },
        )()

    async def _all_products_for_onboarding_sample(self, db, category):
        return list(self._products)

    async def _all_products_for_scoring(self, db, category):
        return list(self._all_scoring_products)

    def _diverse_onboarding_sample(self, candidate_products, game_id, category):
        return list(self._pool_result)

    def _seeded_onboarding_sample(self, candidate_products, game_id, category, model, state):
        return list(self._seeded_result or self._pool_result)

    async def _ensure_model(self, db):
        return _FakeModel()

    def _ensure_redesign_state(self, state):
        normalized = dict(state or {"user_vec": [], "seeded": False})
        normalized.setdefault("current_match_streak", 0)
        normalized.setdefault("longest_match_streak", 0)
        normalized.setdefault("match_streak_target", self.DEFAULT_MATCH_STREAK_TARGET)
        normalized.setdefault("rounds_played", 0)
        normalized.setdefault("total_matches", 0)
        normalized.setdefault("active_preference_ids", [])
        return normalized

    def _align_state_to_feature_space(self, model, state):
        return None

    async def _get_game(self, db, game_id):
        return dict(self._refresh_game)

    def _game_category(self, game):
        return game.get("category", "fountain_pens")

    async def _get_products_by_ids(self, db, ids, projection=None):
        return [self._products_by_id[pid] for pid in ids if pid in self._products_by_id]

    def _feature_projection(self, category):
        return {}

    def _card_projection(self, category):
        return {}

    async def _metrics_for_state(self, db, model, state, selected_ids, category):
        return {
            "coherence_score": float(len(selected_ids)),
            "predicted_prefix_rating": 3.5,
        }

    async def _preference_deck(self, db, game):
        return list(self._preference_deck_result)

    async def _warm_scoring_catalog(self, db, category):
        return None

    def _product_card(self, product, category):
        return {
            "id": str(product["_id"]),
            "title": product.get("title", "Unknown"),
        }

    def _predicted_match_features(self, state, product):
        return ["Test Feature"]

    async def _historical_selection_sequence(self, db, game):
        return []

    async def _current_selection_sequence(self, db, game, include_product_id=None):
        result = list(game.get("onboarding_selected_ids") or [])
        if include_product_id:
            result.append(include_product_id)
        return result

    def _rank_candidates(self, model, state, products, category, disliked_tokens):
        if self._ranked_candidates:
            return list(self._ranked_candidates)
        return [(5.0 - idx * 0.1, product) for idx, product in enumerate(products)]

    def _build_round_candidates(self, game_id, round_number, category, scored):
        return [str(product["_id"]) for _, product in scored[:10]]

    def _is_redesigned_game(self, game):
        return True


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


class GamePlayValidationTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_onboarding_rejects_completed_game(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "completed",
        }

        with self.assertRaisesRegex(ValueError, "already completed"):
            await service.get_onboarding(None, "game-1")

    async def test_submit_onboarding_rejects_if_already_submitted(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": ["p1"],
            "onboarding_pool_ids": ["p1", "p2"],
            "model_state": {},
        }

        with self.assertRaisesRegex(ValueError, "already submitted"):
            await service.submit_onboarding(None, "game-1", ["p1"], 4)

    async def test_submit_onboarding_rejects_duplicate_products(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": [],
            "onboarding_pool_ids": ["p1", "p2"],
            "model_state": {},
        }

        with self.assertRaisesRegex(ValueError, "Duplicate products are not allowed"):
            await service.submit_onboarding(None, "game-1", ["p1", "p1"], 4)

    async def test_submit_onboarding_rejects_when_pool_not_initialized(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": [],
            "onboarding_pool_ids": [],
            "model_state": {},
        }

        with self.assertRaisesRegex(ValueError, "pool is not initialized"):
            await service.submit_onboarding(None, "game-1", ["p1"], 4)

    async def test_submit_onboarding_rejects_selection_outside_pool(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": [],
            "onboarding_pool_ids": ["p1", "p2"],
            "model_state": {},
        }

        with self.assertRaisesRegex(ValueError, "must come from the onboarding pool"):
            await service.submit_onboarding(None, "game-1", ["p3"], 4)

    async def test_start_round_rejects_completed_game(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "model_state": {
                "current_match_streak": 3,
                "match_streak_target": 3,
            },
            "onboarding_selected_ids": ["p1"],
            "status": "completed",
            "current_round": 0,
        }

        with self.assertRaisesRegex(ValueError, "Game is complete"):
            await service.start_round(None, "game-1")

    async def test_submit_pick_rejects_completed_game(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "completed",
            "current_round": 0,
            "model_state": {
                "current_match_streak": 3,
                "match_streak_target": 3,
            },
        }

        with self.assertRaisesRegex(ValueError, "already complete"):
            await service.submit_pick(None, "game-1", 1, "p1")

    async def test_submit_pick_rejects_invalid_round_number(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "playing",
            "current_round": 1,
            "model_state": {
                "current_match_streak": 0,
                "match_streak_target": 3,
            },
        }

        with self.assertRaisesRegex(ValueError, "Invalid round number"):
            await service.submit_pick(None, "game-1", 3, "p1")

    async def test_submit_pick_rejects_when_round_not_started(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "playing",
            "current_round": 0,
            "model_state": {
                "current_match_streak": 0,
                "match_streak_target": 3,
            },
        }

        class _FakeDB:
            async def scalar(self, stmt):
                return None

        with self.assertRaisesRegex(ValueError, "Round has not been started"):
            await service.submit_pick(_FakeDB(), "game-1", 1, "p1")

    async def test_refresh_round_rejects_completed_game(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "completed",
            "current_round": 0,
            "onboarding_selected_ids": ["p1"],
            "model_state": {
                "current_match_streak": 3,
                "match_streak_target": 3,
            },
        }

        class _FakeDB:
            async def scalar(self, stmt):
                return None

        with self.assertRaisesRegex(ValueError, "Game is complete"):
            await service.refresh_round(_FakeDB(), "game-1")


class GamePlaySuccessPathTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_onboarding_pool_uses_seeded_sample_for_beta_mode(self):
        service = _FakeService()
        service._products = [
            {"_id": "p1"},
            {"_id": "p2"},
            {"_id": "p3"},
        ]
        service._pool_result = ["p1", "p2"]
        service._seeded_result = ["p3", "p2"]

        game = {
            "_id": "game-1",
            "mode": "beta",
            "model_state": {"user_vec": [0.5]},
            "onboarding_pool_ids": [],
        }

        with patch("app.services.game_play.get_category_profile", return_value=SimpleNamespace(onboarding_pool_size=2)):
            result = await service._build_onboarding_pool(None, game, "fountain_pens")

        self.assertEqual(result, ["p3", "p2"])

    async def test_get_onboarding_returns_products_and_updates_pool(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_pool_ids": [],
        }
        service._products = [{"_id": "p1"}, {"_id": "p2"}]
        service._pool_result = ["p1", "p2"]
        service._products_by_id = {
            "p1": {"_id": "p1", "title": "Pen 1"},
            "p2": {"_id": "p2", "title": "Pen 2"},
        }

        game_row = SimpleNamespace(onboarding_pool_ids=[], updated_at=None)
        db = _FakeDB([game_row])

        with patch("app.services.game_play.get_category_profile", return_value=SimpleNamespace(onboarding_pool_size=2)):
            result = await service.get_onboarding(db, "game-1")

        self.assertEqual(result["game_id"], "game-1")
        self.assertEqual(result["pool_size"], 2)
        self.assertEqual([product["id"] for product in result["products"]], ["p1", "p2"])
        self.assertEqual(game_row.onboarding_pool_ids, ["p1", "p2"])
        self.assertEqual(db.commits, 1)

    async def test_refresh_onboarding_returns_products_and_updates_pool(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": [],
            "onboarding_pool_ids": ["old1", "old2"],
        }
        service._products = [{"_id": "p1"}, {"_id": "p2"}, {"_id": "p3"}]
        service._pool_result = ["p1", "p2"]
        service._products_by_id = {
            "p1": {"_id": "p1", "title": "Pen 1"},
            "p2": {"_id": "p2", "title": "Pen 2"},
        }

        game_row = SimpleNamespace(onboarding_pool_ids=["old1", "old2"], updated_at=None)
        db = _FakeDB([game_row])

        with patch("app.services.game_play.get_category_profile", return_value=SimpleNamespace(onboarding_pool_size=2)):
            result = await service.refresh_onboarding(db, "game-1", selected_product_ids=["p1"])

        self.assertEqual(result["pool_size"], 2)
        self.assertEqual(result["products"][0]["id"], "p1")
        self.assertEqual(game_row.onboarding_pool_ids[0], "p1")
        self.assertEqual(db.commits, 1)

    async def test_submit_onboarding_success_updates_game_state_and_creates_prefix_rating(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "onboarding",
            "onboarding_selected_ids": [],
            "onboarding_pool_ids": ["p1", "p2"],
            "model_state": {},
        }
        service._products_by_id = {
            "p1": {"_id": "p1", "title": "Pen 1"},
            "p2": {"_id": "p2", "title": "Pen 2"},
        }

        game_row = SimpleNamespace(
            schema_version=None,
            status="onboarding",
            category="fountain_pens",
            model_state=None,
            onboarding_selected_ids=[],
            onboarding_rating=None,
            updated_at=None,
        )
        db = _FakeDB([game_row])

        result = await service.submit_onboarding(db, "game-1", ["p1", "p2"], 4)

        self.assertTrue(result["accepted"])
        self.assertEqual(result["next_round"], 1)
        self.assertEqual(game_row.status, "ready")
        self.assertEqual(game_row.onboarding_selected_ids, ["p1", "p2"])
        self.assertEqual(game_row.onboarding_rating, 4)
        self.assertEqual(db.commits, 1)
        self.assertEqual(len(db.added), 1)

    async def test_start_round_returns_existing_active_round_candidates(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "playing",
            "current_round": 0,
            "onboarding_selected_ids": ["p1"],
            "model_state": {
                "current_match_streak": 1,
                "longest_match_streak": 2,
                "match_streak_target": 3,
                "rounds_played": 1,
            },
        }
        service._products_by_id = {
            "c1": {"_id": "c1", "title": "Candidate 1"},
            "c2": {"_id": "c2", "title": "Candidate 2"},
        }

        round_row = _FakeRoundRow(candidate_ids=["c1", "c2"], completed=False)
        round_row.pre_metrics = {"coherence_score": 0.7, "predicted_prefix_rating": 4.1}
        db = _FakeDB([round_row])

        with patch(
            "app.services.game_play.get_category_profile",
            return_value=SimpleNamespace(
                round_mode="standard",
                round_intro_title="Round Intro",
                round_intro_body="Pick one",
            ),
        ):
            result = await service.start_round(db, "game-1")

        self.assertEqual(result["round_number"], 1)
        self.assertEqual(len(result["candidates"]), 2)
        self.assertEqual(result["candidates"][0]["id"], "c1")
        self.assertEqual(result["pre_round_metrics"]["coherence_score"], 0.7)

    async def test_submit_pick_success_updates_scores_and_completes_game(self):
        service = _FakeService()
        service.recommender.feature_space.feature_index = {"material": 0}
        service.recommender.item_vectors = {
            "c1": np.array([2.0], dtype=np.float32),
            "c2": np.array([-1.0], dtype=np.float32),
        }
        service.recommender.item_norms = {
            "c1": 2.0,
            "c2": 1.0,
        }
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "playing",
            "current_round": 0,
            "human_score": 0,
            "model_state": {
                "user_vec": [1.0],
                "current_match_streak": 0,
                "longest_match_streak": 0,
                "match_streak_target": 1,
                "active_preference_ids": ["seed-1"],
            },
        }
        service._products_by_id = {
            "c1": {"_id": "c1", "title": "Top Pick"},
            "c2": {"_id": "c2", "title": "Other Pick"},
            "d1": {"_id": "d1", "title": "Less Like This"},
        }

        round_row = _FakeRoundRow(candidate_ids=["c1", "c2"], completed=False)
        game_row = SimpleNamespace(
            current_round=0,
            human_score=0,
            ai_score=0,
            status="playing",
            model_state={},
            updated_at=None,
        )
        db = _FakeDB([round_row, game_row])

        result = await service.submit_pick(db, "game-1", 1, "c1", less_like_ids=["d1", "c1"])

        self.assertTrue(result["ai_correct"])
        self.assertTrue(result["ai_exact"])
        self.assertTrue(result["game_complete"])
        self.assertEqual(result["human_points"], 1)
        self.assertEqual(result["ai_points"], 0)
        self.assertEqual(result["current_match_streak"], 1)
        self.assertEqual(result["total_human_score"], 1)
        self.assertEqual(result["ai_pick"]["id"], "c1")
        self.assertIn("Preference Match!", result["ai_explanation"]["reason"])
        self.assertEqual(game_row.status, "completed")
        self.assertEqual(game_row.current_round, 1)
        self.assertEqual(game_row.human_score, 1)
        self.assertEqual(game_row.ai_score, 0)
        self.assertIn("d1", game_row.model_state["disliked_ids"])
        self.assertEqual(db.commits, 1)

    async def test_refresh_round_success_updates_candidates_and_dislikes(self):
        service = _FakeService()
        service._refresh_game = {
            "_id": "game-1",
            "category": "fountain_pens",
            "status": "playing",
            "current_round": 0,
            "onboarding_selected_ids": ["seed-1"],
            "model_state": {
                "user_vec": [0.5],
                "current_match_streak": 0,
                "longest_match_streak": 1,
                "match_streak_target": 3,
                "active_preference_ids": ["seed-1"],
            },
        }
        service._all_scoring_products = [{"_id": f"cand-{idx}", "title": f"Cand {idx}"} for idx in range(12)]
        service._products_by_id = {
            **{f"cand-{idx}": {"_id": f"cand-{idx}", "title": f"Cand {idx}"} for idx in range(12)},
            "less-1": {"_id": "less-1", "title": "Avoid Me"},
        }
        service._ranked_candidates = [
            (5.0 - idx * 0.1, {"_id": f"cand-{idx}", "title": f"Cand {idx}"}) for idx in range(10)
        ]

        round_row = _FakeRoundRow(candidate_ids=["old-1", "old-2"], completed=False)
        game_row = SimpleNamespace(status="playing", model_state={}, updated_at=None)
        db = _FakeDB([round_row, game_row])

        with patch(
            "app.services.game_play.get_category_profile",
            return_value=SimpleNamespace(
                round_mode="standard",
                round_intro_title="New Round",
                round_intro_body="Fresh picks",
            ),
        ):
            result = await service.refresh_round(db, "game-1", less_like_ids=["less-1", "less-1"])

        self.assertEqual(result["round_number"], 1)
        self.assertEqual(len(result["candidates"]), 10)
        self.assertEqual(round_row.candidate_ids, [f"cand-{idx}" for idx in range(10)])
        self.assertIn("less-1", game_row.model_state["disliked_ids"])
        self.assertEqual(game_row.status, "playing")
        self.assertEqual(db.commits, 1)
