import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import patch

from app.services.game_insights import GameInsightsMixin


class _FakeResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return self

    def all(self):
        return self._items


class _FakeDB:
    def __init__(self, scalar_results=None, execute_results=None):
        self.scalar_results = list(scalar_results or [])
        self.execute_results = list(execute_results or [])

    async def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def execute(self, _stmt):
        if self.execute_results:
            return _FakeResult(self.execute_results.pop(0))
        return _FakeResult([])


class _FakeModel:
    def init_state(self):
        return {"user_vec": [], "total_matches": 0, "longest_match_streak": 0}

    def detect_hidden_preferences(self, state, selected_products):
        return []

    def get_hidden_gem_products(self, state, selected_products, all_products, top_n=10):
        return []


class _FakeFeatureSpace:
    def __init__(self):
        self.feature_index = {}

    def vectorize(self, product):
        return []


class _FakeRecommender:
    def __init__(self):
        self.feature_space = _FakeFeatureSpace()


class _FakeInsightsService(GameInsightsMixin):
    LEGACY_SCHEMA_VERSION = 1
    REDESIGN_SCHEMA_VERSION = 3
    MAX_ONBOARDING_SELECTIONS = 10

    def __init__(self):
        self.recommender = _FakeRecommender()
        self._game = None
        self._preference_deck_result = [{"id": "pref-1"}]
        self._selection_sequence = []
        self._all_products = []
        self._products_by_ids = []
        self._ranked_candidates = []
        self._is_redesigned = True
        self._rounds_played_value = 0
        self._match_progress_value = (0, 0, 3)

    async def _get_game(self, db, game_id):
        return dict(self._game)

    async def _ensure_model(self, db):
        return _FakeModel()

    def _game_category(self, game):
        return game.get("category", "fountain_pens")

    def _is_redesigned_game(self, game):
        return self._is_redesigned

    def _ensure_redesign_state(self, state):
        return dict(state or {"user_vec": [], "total_matches": 0, "longest_match_streak": 0})

    def _align_state_to_feature_space(self, model, state):
        return False

    async def _preference_deck(self, db, game):
        return list(self._preference_deck_result)

    def _match_progress(self, game):
        return self._match_progress_value

    def _rounds_played(self, game):
        return self._rounds_played_value

    async def _current_selection_sequence(self, db, game):
        return list(self._selection_sequence)

    async def _all_products_for_scoring(self, db, category):
        return list(self._all_products)

    def _rank_candidates(self, model, state, products, category, disliked_tokens):
        return list(self._ranked_candidates)

    def _product_card(self, product, category):
        return {
            "id": str(product["_id"]),
            "title": product.get("title", "Unknown"),
        }

    def _feature_projection(self, category):
        return {}

    async def _get_products_by_ids(self, db, ids, projection=None):
        wanted = set(ids)
        return [product for product in self._products_by_ids if str(product["_id"]) in wanted]


class GameInsightsHelperTests(unittest.TestCase):
    def test_humanize_feature_list_delegates(self):
        from unittest.mock import patch
        from app.services.game_insights import humanize_feature_list

        raw = [("feature_a", 0.5)]
        expected = [("Feature A", 0.5)]

        with patch("app.services.game_insights.profile_humanize_feature_list", return_value=expected) as mock_helper:
            result = humanize_feature_list(raw)

        self.assertEqual(result, expected)
        mock_helper.assert_called_once_with(raw)


class GameInsightsMixinTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_game_summary_rejects_incomplete_game(self):
        service = _FakeInsightsService()
        service._game = {
            "_id": "game-1",
            "player_name": "Sai",
            "category": "fountain_pens",
            "status": "playing",
            "model_state": {},
        }

        with self.assertRaisesRegex(ValueError, "not yet completed"):
            await service.get_game_summary(_FakeDB(), "game-1")

    async def test_get_game_status_returns_progress_and_active_round(self):
        service = _FakeInsightsService()
        service._game = {
            "_id": "game-1",
            "schema_version": 3,
            "player_name": "Sai",
            "category": "fountain_pens",
            "mode": "classic",
            "status": "playing",
            "current_round": 2,
            "total_rounds": 10,
            "human_score": 2,
            "ai_score": 0,
            "onboarding_selected_ids": ["a", "b", "c"],
        }
        service._match_progress_value = (2, 2, 3)
        service._rounds_played_value = 2

        active_round = SimpleNamespace(round_number=3)
        db = _FakeDB(scalar_results=[active_round])

        result = await service.get_game_status(db, "game-1")

        self.assertEqual(result["id"], "game-1")
        self.assertEqual(result["player_name"], "Sai")
        self.assertEqual(result["category"], "fountain_pens")
        self.assertEqual(result["current_match_streak"], 2)
        self.assertEqual(result["longest_match_streak"], 2)
        self.assertEqual(result["match_streak_target"], 3)
        self.assertEqual(result["round_in_progress"], 3)
        self.assertTrue(result["onboarding_complete"])
        self.assertEqual(result["onboarding_selected_count"], 3)

    async def test_get_leaderboard_returns_best_game_per_player(self):
        service = _FakeInsightsService()
        service._rounds_played_value = 2

        game_a_worse = SimpleNamespace(
            id="g1",
            player_name="Alice",
            category="fountain_pens",
            status="completed",
            schema_version=3,
            human_score=2,
            ai_score=1,
            current_round=3,
            model_state={"total_matches": 2, "longest_match_streak": 1},
            created_at=datetime(2026, 1, 1),
            updated_at=datetime(2026, 1, 2),
        )
        game_a_better = SimpleNamespace(
            id="g2",
            player_name="Alice",
            category="fountain_pens",
            status="completed",
            schema_version=3,
            human_score=3,
            ai_score=0,
            current_round=2,
            model_state={"total_matches": 2, "longest_match_streak": 2},
            created_at=datetime(2026, 1, 3),
            updated_at=datetime(2026, 1, 4),
        )
        game_b = SimpleNamespace(
            id="g3",
            player_name="Bob",
            category="fountain_pens",
            status="completed",
            schema_version=3,
            human_score=2,
            ai_score=0,
            current_round=4,
            model_state={"total_matches": 2, "longest_match_streak": 1},
            created_at=datetime(2026, 1, 5),
            updated_at=datetime(2026, 1, 6),
        )

        db = _FakeDB(execute_results=[[game_a_worse, game_a_better, game_b]])

        with patch("app.services.game_insights.record_to_dict", side_effect=lambda row: {"_id": row.id, **row.__dict__}):
            result = await service.get_leaderboard(db, limit=10, category="fountain_pens")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0]["player_name"], "Alice")
        self.assertEqual(result[0]["rounds_to_complete"], 2)
        self.assertEqual(result[0]["rank"], 1)
        self.assertEqual(result[1]["player_name"], "Bob")
        self.assertEqual(result[1]["rank"], 2)

    async def test_get_player_history_returns_completed_games(self):
        service = _FakeInsightsService()
        service._is_redesigned = True
        service._rounds_played_value = 4

        game_row = SimpleNamespace(
            id="g1",
            player_name="Sai",
            category="fountain_pens",
            status="completed",
            schema_version=3,
            human_score=3,
            ai_score=1,
            current_round=4,
            model_state={"total_matches": 3, "longest_match_streak": 2},
            created_at=datetime(2026, 2, 1),
            updated_at=datetime(2026, 2, 2),
        )

        db = _FakeDB(execute_results=[[game_row]])

        with patch("app.services.game_insights.record_to_dict", side_effect=lambda row: {"_id": row.id, **row.__dict__}):
            result = await service.get_player_history(db, "Sai", limit=20, category="fountain_pens")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["game_id"], "g1")
        self.assertEqual(result[0]["player_name"], "Sai")
        self.assertEqual(result[0]["rounds_played"], 4)
        self.assertAlmostEqual(result[0]["ai_accuracy"], 3 / 4)
        self.assertEqual(result[0]["longest_match_streak"], 2)

    async def test_get_player_history_uses_db_count_for_legacy_games(self):
        service = _FakeInsightsService()
        service._is_redesigned = False

        legacy_game = SimpleNamespace(
            id="legacy-1",
            player_name="Sai",
            category="fountain_pens",
            status="completed",
            schema_version=1,
            human_score=2,
            ai_score=2,
            current_round=4,
            model_state={},
            created_at=datetime(2026, 3, 1),
            updated_at=datetime(2026, 3, 2),
        )

        # execute() returns the history rows; scalar() returns the ai_correct count
        db = _FakeDB(
            scalar_results=[2],
            execute_results=[[legacy_game]],
        )

        with patch("app.services.game_insights.record_to_dict", side_effect=lambda row: {"_id": row.id, **row.__dict__}):
            result = await service.get_player_history(db, "Sai", limit=20, category="fountain_pens")

        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]["game_id"], "legacy-1")
        self.assertEqual(result[0]["rounds_played"], 4)
        self.assertAlmostEqual(result[0]["ai_accuracy"], 2 / 4)
        self.assertEqual(result[0]["rounds_to_complete"], 0)


class GameInsightsSummaryTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_game_summary_returns_completed_summary_payload(self):
        service = _FakeInsightsService()
        service._game = {
            "_id": "game-1",
            "schema_version": 3,
            "player_name": "Sai",
            "category": "fountain_pens",
            "mode": "classic",
            "status": "completed",
            "human_score": 2,
            "ai_score": 1,
            "current_round": 3,
            "model_state": {
                "user_vec": [0.9, -0.4],
                "total_matches": 2,
                "longest_match_streak": 2,
            },
        }
        service._rounds_played_value = 3
        service._match_progress_value = (0, 2, 3)
        service._selection_sequence = ["p1", "p2"]
        service._all_products = [
            {"_id": "r1", "title": "Rec 1"},
            {"_id": "r2", "title": "Rec 2"},
            {"_id": "r3", "title": "Rec 3"},
        ]
        service._products_by_ids = [
            {"_id": "p1", "title": "Picked 1"},
            {"_id": "p2", "title": "Picked 2"},
        ]
        service._ranked_candidates = [
            (4.9, {"_id": "r1", "title": "Rec 1"}),
            (4.7, {"_id": "r2", "title": "Rec 2"}),
            (4.5, {"_id": "r3", "title": "Rec 3"}),
        ]

        service.recommender.feature_space.feature_index = {
            "feature_like": 0,
            "feature_dislike": 1,
        }

        round_rows = [
            SimpleNamespace(
                round_number=1,
                ai_correct=True,
                ai_pick_id="p1",
                human_pick_id="p1",
                ai_rank_of_pick=1,
                ai_confidence=4.8,
                ai_points=0,
                human_points=1,
                post_metrics={"coherence_score": 0.8, "predicted_prefix_rating": 4.2},
            ),
            SimpleNamespace(
                round_number=2,
                ai_correct=True,
                ai_pick_id="x2",
                human_pick_id="p2",
                ai_rank_of_pick=2,
                ai_confidence=4.3,
                ai_points=0,
                human_points=1,
                post_metrics={"coherence_score": 0.85, "predicted_prefix_rating": 4.0},
            ),
            SimpleNamespace(
                round_number=3,
                ai_correct=False,
                ai_pick_id="x3",
                human_pick_id="p3",
                ai_rank_of_pick=6,
                ai_confidence=3.9,
                ai_points=1,
                human_points=0,
                post_metrics={"coherence_score": 0.75, "predicted_prefix_rating": 3.8},
            ),
        ]

        db = _FakeDB(execute_results=[round_rows])

        model = _FakeModel()
        model.detect_hidden_preferences = lambda state, products: []
        model.get_hidden_gem_products = lambda state, selected_products, all_products, top_n=10: []

        async def fake_ensure_model(_db):
            return model

        service._ensure_model = fake_ensure_model

        with patch(
            "app.services.game_insights.humanize_feature_list",
            side_effect=lambda raw: raw,
        ):
            result = await service.get_game_summary(db, "game-1")

        self.assertEqual(result["game_id"], "game-1")
        self.assertEqual(result["player_name"], "Sai")
        self.assertEqual(result["total_rounds"], 3)
        self.assertEqual(result["rounds_played"], 3)
        self.assertEqual(result["total_matches"], 2)
        self.assertAlmostEqual(result["match_rate"], 2 / 3)
        self.assertEqual(result["accuracy"]["top3_correct"], 2)
        self.assertEqual(result["accuracy"]["exact_correct"], 1)
        self.assertEqual(len(result["round_stats"]), 3)
        self.assertEqual(len(result["top5_recommendations"]), 3)
        self.assertEqual(result["top5_recommendations"][0]["id"], "r1")

    async def test_get_game_summary_filters_hidden_preferences_already_in_learned_likes(self):
        service = _FakeInsightsService()
        service._game = {
            "_id": "game-2",
            "schema_version": 3,
            "player_name": "Sai",
            "category": "fountain_pens",
            "mode": "classic",
            "status": "completed",
            "human_score": 1,
            "ai_score": 0,
            "current_round": 1,
            "model_state": {
                "user_vec": [0.8],
                "total_matches": 1,
                "longest_match_streak": 1,
            },
        }
        service._rounds_played_value = 1
        service._match_progress_value = (0, 1, 3)
        service._selection_sequence = ["p1"]
        service._all_products = [{"_id": "r1", "title": "Rec 1"}]
        service._products_by_ids = [{"_id": "p1", "title": "Picked 1"}]
        service._ranked_candidates = [(4.9, {"_id": "r1", "title": "Rec 1"})]

        service.recommender.feature_space.feature_index = {
            "liked_feature": 0,
        }

        round_rows = [
            SimpleNamespace(
                round_number=1,
                ai_correct=True,
                ai_pick_id="p1",
                human_pick_id="p1",
                ai_rank_of_pick=1,
                ai_confidence=4.5,
                ai_points=0,
                human_points=1,
                post_metrics={"coherence_score": 0.8, "predicted_prefix_rating": 4.2},
            ),
        ]

        db = _FakeDB(execute_results=[round_rows])

        model = _FakeModel()
        model.detect_hidden_preferences = lambda state, products: [
            {"feature": "liked_feature", "latency": 0.9},
            {"feature": "different_hidden", "latency": 0.7},
        ]
        model.get_hidden_gem_products = lambda state, selected_products, all_products, top_n=10: []

        async def fake_ensure_model(_db):
            return model

        service._ensure_model = fake_ensure_model

        with patch(
            "app.services.game_insights.humanize_feature_list",
            side_effect=lambda raw: [(item[0].replace("_", " ").title(), item[1]) for item in raw],
        ):
            result = await service.get_game_summary(db, "game-2")

        hidden_names = [name for name, _ in result["hidden_preferences"]]
        self.assertIn("Different Hidden", hidden_names)
        self.assertNotIn("Liked Feature", hidden_names)

    async def test_get_game_summary_builds_hidden_gems_explanation(self):
        service = _FakeInsightsService()
        service._game = {
            "_id": "game-3",
            "schema_version": 3,
            "player_name": "Sai",
            "category": "fountain_pens",
            "mode": "classic",
            "status": "completed",
            "human_score": 1,
            "ai_score": 0,
            "current_round": 1,
            "model_state": {
                "user_vec": [0.8],
                "total_matches": 1,
                "longest_match_streak": 1,
            },
        }
        service._rounds_played_value = 1
        service._match_progress_value = (0, 1, 3)
        service._selection_sequence = ["p1"]
        service._all_products = [
            {"_id": "r1", "title": "Top Rec"},
            {"_id": "g1", "title": "Hidden Gem 1"},
            {"_id": "g2", "title": "Hidden Gem 2"},
        ]
        service._products_by_ids = [{"_id": "p1", "title": "Picked 1"}]
        service._ranked_candidates = [(4.9, {"_id": "r1", "title": "Top Rec"})]

        service.recommender.feature_space.feature_index = {
            "feature_a": 0,
        }

        round_rows = [
            SimpleNamespace(
                round_number=1,
                ai_correct=True,
                ai_pick_id="p1",
                human_pick_id="p1",
                ai_rank_of_pick=1,
                ai_confidence=4.5,
                ai_points=0,
                human_points=1,
                post_metrics={"coherence_score": 0.8, "predicted_prefix_rating": 4.2},
            ),
        ]

        db = _FakeDB(execute_results=[round_rows])

        model = _FakeModel()
        model.detect_hidden_preferences = lambda state, products: [
            {"feature": "hidden_alpha", "latency": 0.9},
            {"feature": "hidden_beta", "latency": 0.8},
        ]
        model.get_hidden_gem_products = lambda state, selected_products, all_products, top_n=10: [
            (4.2, {"_id": "g1", "title": "Hidden Gem 1"}, ["hidden_alpha"]),
            (4.1, {"_id": "g2", "title": "Hidden Gem 2"}, ["hidden_beta"]),
        ]

        async def fake_ensure_model(_db):
            return model

        service._ensure_model = fake_ensure_model

        with patch(
            "app.services.game_insights.humanize_feature_list",
            side_effect=lambda raw: [(item[0].replace("_", " ").title(), item[1]) for item in raw],
        ):
            result = await service.get_game_summary(db, "game-3")

        self.assertEqual(len(result["hidden_gems_products"]), 2)
        self.assertIn("Hidden Alpha", result["hidden_gems_explanation"])
        self.assertIn("Hidden Beta", result["hidden_gems_explanation"])
