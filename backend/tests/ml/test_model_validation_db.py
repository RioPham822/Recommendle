import os
import unittest

from sqlalchemy import func, select

from app.db import GameRoundRecord, ProductRecord, get_session_factory, record_to_dict
from app.ml.pbcf_nmf import PBCFEngine
from app.services.recommender import Recommender

TRUE_VALUES = {"1", "true", "yes", "on"}
DB_INTEGRATION_ENABLED = os.getenv("MODEL_VALIDATION_DB_INTEGRATION", "").strip().lower() in TRUE_VALUES


@unittest.skipUnless(
    DB_INTEGRATION_ENABLED,
    "Set MODEL_VALIDATION_DB_INTEGRATION=1 to run live Postgres movie model integration tests",
)
class TestMovieModelDbIntegration(unittest.IsolatedAsyncioTestCase):
    async def test_recommender_refresh_builds_feature_space_from_live_db(self):
        session_factory = get_session_factory()
        async with session_factory() as db:
            movie_count = int(
                (
                    await db.scalar(
                        select(func.count()).select_from(ProductRecord).where(ProductRecord.category == "movies")
                    )
                )
                or 0
            )
            if movie_count < 10:
                self.skipTest("Need at least 10 movie products in Postgres for DB-backed validation")

            recommender = Recommender()
            await recommender.refresh(db)

            self.assertIsNotNone(recommender.feature_space)
            self.assertIsNotNone(recommender.model)
            self.assertGreater(len(recommender.item_vectors), 0)

    async def test_recommender_recommend_does_not_crash_on_live_db_rows(self):
        session_factory = get_session_factory()
        async with session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(ProductRecord).where(ProductRecord.category == "movies").order_by(ProductRecord.created_at.desc()).limit(6)
                    )
                )
                .scalars()
                .all()
            )
            if len(rows) < 4:
                self.skipTest("Need at least 4 movie products in Postgres for live recommendation validation")

            recommender = Recommender()
            await recommender.refresh(db)
            await recommender.ensure_fresh(db)

            selected_ids = [str(row.id) for row in rows[:2]]
            game = {
                "_id": "movie-db-integration",
                "onboarding_selected_ids": selected_ids,
                "model_state": recommender.model.init_state() if recommender.model else {},
            }
            result = await recommender.recommend(db, "movie-db-integration", game, limit=3)

            strong_ids = [str(product.id) for product in result["strong"]]
            self.assertGreater(len(strong_ids), 0)
            self.assertEqual(len(strong_ids), len(set(strong_ids)))

    async def test_pbcf_trains_when_completed_rounds_exist(self):
        session_factory = get_session_factory()
        async with session_factory() as db:
            completed_rounds = int(
                (
                    await db.scalar(
                        select(func.count()).select_from(GameRoundRecord).where(GameRoundRecord.completed.is_(True))
                    )
                )
                or 0
            )
            if completed_rounds == 0:
                self.skipTest("Need completed game rounds in Postgres for PBCF integration validation")

            engine = PBCFEngine(k=6, iters=10, seed=42)
            await engine.train(db)
            stats = engine.get_stats()

            self.assertTrue(stats["trained"])
            self.assertGreater(stats["ratings_count"], 0)

    async def test_live_movie_rows_with_missing_fields_still_vectorize(self):
        session_factory = get_session_factory()
        async with session_factory() as db:
            rows = (
                (
                    await db.execute(
                        select(ProductRecord).where(ProductRecord.category == "movies").order_by(ProductRecord.created_at.desc()).limit(50)
                    )
                )
                .scalars()
                .all()
            )
            sparse_rows = []
            for row in rows:
                record = record_to_dict(row)
                if not record.get("genres") or record.get("vendor") is None or not record.get("keywords"):
                    sparse_rows.append(row)
            if not sparse_rows:
                self.skipTest("No sparse movie rows found in Postgres for missing-field integration validation")

            recommender = Recommender()
            await recommender.refresh(db)
            assert recommender.feature_space is not None

            for row in sparse_rows:
                record = record_to_dict(row)
                product_id = str(record.get("_id"))
                vector = recommender.item_vectors.get(product_id)
                if vector is None:
                    vector = recommender.feature_space.vectorize(record)
                self.assertEqual(len(vector), len(recommender.feature_space.feature_index))


if __name__ == "__main__":
    unittest.main()
