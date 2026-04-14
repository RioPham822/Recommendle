import unittest
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock, patch

import numpy as np

from app.services.recommender import Recommender


class _FakeScalarResult:
    def __init__(self, items):
        self._items = items

    def all(self):
        return self._items


class _FakeExecuteResult:
    def __init__(self, items):
        self._items = items

    def scalars(self):
        return _FakeScalarResult(self._items)


class _FakeDB:
    def __init__(self, *, scalar_results=None, execute_results=None):
        self.scalar_results = list(scalar_results or [])
        self.execute_results = list(execute_results or [])
        self.commits = 0

    async def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    async def execute(self, _stmt):
        if self.execute_results:
            return _FakeExecuteResult(self.execute_results.pop(0))
        return _FakeExecuteResult([])

    async def commit(self):
        self.commits += 1


class _FakeProduct:
    def __init__(self, product_id, title):
        self.id = product_id
        self.title = title


class RecommenderTests(unittest.IsolatedAsyncioTestCase):
    def test_invalidate_ratings_sets_stale_marker(self):
        recommender = Recommender()
        recommender._rating_count = 5

        recommender.invalidate_ratings()

        self.assertEqual(recommender._rating_count, -1)

    def test_load_state_returns_existing_state(self):
        recommender = Recommender()
        existing = {"bias": 1.2}

        result = recommender.load_state({"model_state": existing})

        self.assertEqual(result, existing)

    def test_load_state_uses_model_init_when_state_missing(self):
        recommender = Recommender()
        recommender.model = Mock()
        recommender.model.init_state.return_value = {"user_vec": [], "bias": 0.0}

        result = recommender.load_state({"model_state": {}})

        self.assertEqual(result, {"user_vec": [], "bias": 0.0})
        recommender.model.init_state.assert_called_once()

    async def test_save_state_updates_game_and_commits(self):
        recommender = Recommender()
        game_row = SimpleNamespace(model_state=None)
        db = _FakeDB(scalar_results=[game_row])

        await recommender.save_state(db, "game-1", {"bias": 2.0})

        self.assertEqual(game_row.model_state, {"bias": 2.0})
        self.assertEqual(db.commits, 1)

    async def test_ensure_fresh_refreshes_when_model_missing(self):
        recommender = Recommender()
        db = _FakeDB(scalar_results=[3])
        recommender.refresh = AsyncMock()

        await recommender.ensure_fresh(db)

        recommender.refresh.assert_awaited_once_with(db)

    async def test_ensure_fresh_refreshes_when_product_count_changes(self):
        recommender = Recommender()
        recommender.feature_space = object()
        recommender.model = object()
        recommender._product_count = 2
        db = _FakeDB(scalar_results=[5])
        recommender.refresh = AsyncMock()

        await recommender.ensure_fresh(db)

        recommender.refresh.assert_awaited_once_with(db)

    async def test_ensure_fresh_skips_refresh_when_catalog_matches(self):
        recommender = Recommender()
        recommender.feature_space = object()
        recommender.model = object()
        recommender._product_count = 4
        db = _FakeDB(scalar_results=[4])
        recommender.refresh = AsyncMock()

        await recommender.ensure_fresh(db)

        recommender.refresh.assert_not_awaited()

    async def test_get_pbcf_stats_refreshes_and_returns_stats(self):
        recommender = Recommender()
        recommender._refresh_pbcf = AsyncMock()
        recommender.pbcf = Mock()
        recommender.pbcf.get_stats.return_value = {"trained": True, "ratings": 7}

        result = await recommender.get_pbcf_stats(_FakeDB())

        recommender._refresh_pbcf.assert_awaited_once()
        self.assertEqual(result, {"trained": True, "ratings": 7})

    async def test_recommend_returns_strong_and_wildcard_results(self):
        recommender = Recommender()
        recommender.model = Mock()
        recommender.model.score_item.side_effect = lambda state, vec: float(vec[0])
        recommender.model.coherence_score.return_value = 0.75
        recommender.model.predict_prefix_rating.return_value = 4.2

        recommender._refresh_pbcf = AsyncMock()
        recommender.refresh = AsyncMock()

        recommender.item_vectors = {
            "p2": np.array([0.9], dtype=np.float32),
            "p3": np.array([0.4], dtype=np.float32),
            "p4": np.array([0.2], dtype=np.float32),
        }

        fake_products = [
            SimpleNamespace(id="p2", title="Pen 2"),
            SimpleNamespace(id="p3", title="Pen 3"),
            SimpleNamespace(id="p4", title="Pen 4"),
        ]

        db = _FakeDB(
            execute_results=[
                [],
                fake_products,
            ]
        )

        recommender.pbcf = Mock()
        recommender.pbcf.predict_user_ratings = AsyncMock(return_value={})

        game = {
            "_id": "game-1",
            "onboarding_selected_ids": ["p1"],
            "model_state": {"user_vec": [1.0], "bias": 0.0},
        }

        with patch(
            "app.services.recommender.record_to_dict",
            side_effect=lambda row: {"id": row.id, "title": row.title},
        ), patch(
            "app.services.recommender.Product",
            side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
        ), patch(
            "app.services.recommender.random.choice", side_effect=lambda seq: seq[0]
        ):
            result = await recommender.recommend(db, "game-1", game, limit=2)

        self.assertEqual(len(result["strong"]), 2)
        self.assertEqual(result["strong"][0].id, "p2")
        self.assertEqual(result["strong"][1].id, "p3")
        self.assertIsNotNone(result["wildcard"])
        self.assertEqual(result["coherence_score"], 0.75)
        self.assertEqual(result["predicted_prefix_rating"], 4.2)

    async def test_recommend_prefers_pbcf_score_when_available(self):
        recommender = Recommender()
        recommender.model = Mock()
        recommender.model.score_item.return_value = 0.1
        recommender.model.coherence_score.return_value = 0.5
        recommender.model.predict_prefix_rating.return_value = 3.5

        recommender._refresh_pbcf = AsyncMock()
        recommender.refresh = AsyncMock()

        recommender.item_vectors = {
            "p2": np.array([0.2], dtype=np.float32),
        }

        fake_products = [
            SimpleNamespace(id="p2", title="Pen 2"),
        ]

        db = _FakeDB(
            execute_results=[
                [],
                fake_products,
            ]
        )

        recommender.pbcf = Mock()
        recommender.pbcf.predict_user_ratings = AsyncMock(return_value={"p2": 4.8})

        game = {
            "_id": "game-1",
            "onboarding_selected_ids": [],
            "model_state": {"user_vec": [1.0]},
        }

        with patch(
            "app.services.recommender.record_to_dict",
            side_effect=lambda row: {"id": row.id, "title": row.title},
        ), patch(
            "app.services.recommender.Product",
            side_effect=lambda **kwargs: SimpleNamespace(**kwargs),
        ), patch(
            "app.services.recommender.random.choice", side_effect=lambda seq: seq[0]
        ):
            result = await recommender.recommend(db, "game-1", game, limit=1)

        self.assertEqual(len(result["strong"]), 1)
        self.assertEqual(result["strong"][0].id, "p2")
        recommender.model.score_item.assert_called_once()
