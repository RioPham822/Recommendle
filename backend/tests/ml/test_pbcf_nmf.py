import unittest
from datetime import datetime, timedelta

import numpy as np

from app.ml.pbcf_nmf import PBCFArtifacts, PBCFEngine


class _FakeScalarResult:
    def __init__(self, rows):
        self._rows = rows

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)


class _FakeDB:
    def __init__(self, rows):
        self._rows = rows

    async def execute(self, _stmt):
        return _FakeScalarResult(self._rows)


class _Round:
    def __init__(self, game_id, candidate_ids, ai_correct, created_at, completed=True):
        self.game_id = game_id
        self.candidate_ids = candidate_ids
        self.ai_correct = ai_correct
        self.created_at = created_at
        self.completed = completed


class PBCFEngineTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_prefix_from_round_sorts_candidate_ids(self):
        engine = PBCFEngine()

        prefix = await engine._build_prefix_from_game_round({"candidate_ids": ["b", "a", "10"]})

        self.assertEqual(prefix, "10-a-b")

    async def test_build_matrix_keeps_latest_rating_per_prefix_and_user(self):
        engine = PBCFEngine()
        now = datetime.utcnow()
        db = _FakeDB(
            [
                _Round("user-1", ["b", "a"], False, now - timedelta(minutes=10)),
                _Round("user-1", ["a", "b"], True, now),
                _Round("user-2", ["x"], False, now - timedelta(minutes=5)),
                _Round("user-3", None, True, now),
            ]
        )

        artifacts = await engine.build_matrix(db)

        self.assertIsNotNone(artifacts)
        self.assertEqual(artifacts.prefix_keys, ["a-b", "x"])
        self.assertEqual(artifacts.user_ids, ["user-1", "user-2"])
        self.assertEqual(artifacts.ratings.shape, (2, 2))
        self.assertEqual(float(artifacts.ratings[0, 0]), 5.0)
        self.assertEqual(float(artifacts.ratings[1, 1]), 1.0)
        self.assertTrue(np.isnan(artifacts.ratings[0, 1]))

    async def test_train_and_predict_user_ratings(self):
        engine = PBCFEngine(k=3, iters=8, seed=7)
        now = datetime.utcnow()
        db = _FakeDB(
            [
                _Round("user-1", ["a"], True, now - timedelta(minutes=3)),
                _Round("user-1", ["b"], False, now - timedelta(minutes=2)),
                _Round("user-2", ["a"], True, now - timedelta(minutes=1)),
                _Round("user-2", ["c"], True, now),
            ]
        )

        await engine.train(db)
        predictions = await engine.predict_user_ratings(db, "user-1")

        self.assertEqual(set(predictions.keys()), {"a", "b", "c"})
        for value in predictions.values():
            self.assertGreaterEqual(value, 1.0)
            self.assertLessEqual(value, 5.0)

    async def test_get_stats_reports_untrained_and_trained_states(self):
        engine = PBCFEngine()

        self.assertEqual(
            engine.get_stats(),
            {
                "trained": False,
                "prefix_count": 0,
                "user_count": 0,
                "ratings_count": 0,
                "missing_ratio": 1.0,
                "latent_dim": 6,
            },
        )

        engine.artifacts = PBCFArtifacts(
            prefix_keys=["p1", "p2"],
            user_ids=["u1"],
            ratings=np.array([[5.0], [np.nan]], dtype=np.float32),
            mask=np.array([[True], [False]]),
        )
        engine.W = np.ones((2, 1), dtype=np.float32)

        self.assertEqual(
            engine.get_stats(),
            {
                "trained": True,
                "prefix_count": 2,
                "user_count": 1,
                "ratings_count": 1,
                "missing_ratio": 0.5,
                "latent_dim": 1,
            },
        )


if __name__ == "__main__":
    unittest.main()
