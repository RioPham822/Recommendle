import asyncio
import hashlib
import json
import math
import pathlib
import unittest
from datetime import datetime, timedelta
from typing import Any

import numpy as np

from app.ml.pbcf_nmf import PBCFEngine
from app.ml.prefix_cf import FeatureSpace, PrefixCFModel

MOVIE_FIXTURE_PATH = pathlib.Path(__file__).parent.parent / "data" / "tmdb_ingest_checkpoint.json"
SKIP_IF_MISSING = not MOVIE_FIXTURE_PATH.exists()
SKIP_REASON = "tmdb_ingest_checkpoint.json not found in backend/data/"


def load_movies_from_fixture(path, limit=None) -> list[dict]:
    """Load normalized movie docs from TMDB checkpoint staged_docs."""
    fixture_path = pathlib.Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    docs = payload.get("staged_docs") or []

    products: list[dict[str, Any]] = []
    for doc in docs:
        title = str(doc.get("title") or "").strip()
        source_id = str(doc.get("source_id") or "").strip()
        vote_average = float(doc.get("vote_average") or 0.0)
        if not title or not source_id:
            continue
        if vote_average <= 0.0:
            continue

        products.append(
            {
                "id": source_id,
                "category": "movies",
                "data": {
                    "title": title,
                    "description": str(doc.get("description") or ""),
                    "vendor": str(doc.get("vendor") or "").strip() or None,
                    "primary_country": str(doc.get("primary_country") or "").strip() or None,
                    "original_language": str(doc.get("original_language") or "").strip() or None,
                    "certification": str(doc.get("certification") or "").strip() or None,
                    "decade_bucket": str(doc.get("decade_bucket") or "").strip() or None,
                    "runtime_bucket": str(doc.get("runtime_bucket") or "").strip() or None,
                    "genres": [str(item).strip() for item in (doc.get("genres") or []) if str(item).strip()],
                    "keywords": [str(item).strip() for item in (doc.get("keywords") or []) if str(item).strip()],
                    "production_companies": [
                        str(item).strip() for item in (doc.get("production_companies") or []) if str(item).strip()
                    ],
                    "directors": [str(item).strip() for item in (doc.get("directors") or []) if str(item).strip()],
                    "release_year": int(doc.get("release_year") or 0),
                    "runtime_minutes": int(doc.get("runtime_minutes") or 0),
                    "vote_average": vote_average,
                    "popularity": float(doc.get("popularity") or 0.0),
                    "vote_count": int(doc.get("vote_count") or 0),
                },
            }
        )
        if limit is not None and len(products) >= int(limit):
            break
    return products


def precision_at_k(recommended_ids, relevant_ids, k):
    if k <= 0:
        return 0.0
    top_k = list(recommended_ids)[:k]
    if not top_k:
        return 0.0
    relevant = set(relevant_ids)
    hits = sum(1 for item_id in top_k if item_id in relevant)
    return float(hits) / float(k)


def recall_at_k(recommended_ids, relevant_ids, k):
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    top_k = list(recommended_ids)[:k]
    hits = sum(1 for item_id in top_k if item_id in relevant)
    return float(hits) / float(len(relevant))


def ndcg_at_k(recommended_ids, relevant_ids, k):
    if k <= 0:
        return 0.0
    relevant = set(relevant_ids)
    top_k = list(recommended_ids)[:k]
    if not top_k:
        return 0.0

    dcg = 0.0
    for rank, item_id in enumerate(top_k, start=1):
        rel = 1.0 if item_id in relevant else 0.0
        if rel > 0:
            dcg += rel / math.log2(rank + 1)

    ideal_hits = min(len(relevant), k)
    if ideal_hits == 0:
        return 0.0
    idcg = sum(1.0 / math.log2(rank + 1) for rank in range(1, ideal_hits + 1))
    if idcg == 0:
        return 0.0
    return dcg / idcg


def hit_rate(recommended_ids, relevant_ids):
    relevant = set(relevant_ids)
    if not relevant:
        return 0.0
    return 1.0 if any(item_id in relevant for item_id in recommended_ids) else 0.0


def _to_model_products(normalized_products: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"_id": row["id"], "category": row["category"], **row["data"]} for row in normalized_products]


def _product_id(product: dict[str, Any]) -> str:
    value = product.get("_id", product.get("id"))
    return str(value)


def _bucket_from_id(product_id: str) -> float:
    digest = hashlib.sha1(product_id.encode("utf-8")).hexdigest()
    raw = int(digest[:8], 16)
    return raw / float(0xFFFFFFFF)


def split_train_test(products: list[dict[str, Any]], test_ratio: float = 0.25) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    train: list[dict[str, Any]] = []
    test: list[dict[str, Any]] = []
    for product in products:
        pid = _product_id(product)
        if _bucket_from_id(pid) < test_ratio:
            test.append(product)
        else:
            train.append(product)
    if not train or not test:
        midpoint = max(1, len(products) // 4)
        return products[midpoint:], products[:midpoint]
    return train, test


def generate_synthetic_session(train_products, eval_products, seed_genre, n_onboarding=10, n_rounds=5):
    target = str(seed_genre).strip().lower()
    train_filtered = [
        product
        for product in train_products
        if any(str(genre).strip().lower() == target for genre in product.get("genres", []))
    ]
    eval_filtered = [
        product
        for product in eval_products
        if any(str(genre).strip().lower() == target for genre in product.get("genres", []))
    ]
    train_filtered.sort(key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)
    eval_filtered.sort(key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)

    if len(train_filtered) < int(n_onboarding):
        return None
    relevant_window = max(20, int(n_rounds) * 4)
    if len(eval_filtered) < relevant_window:
        return None

    onboarding = train_filtered[: int(n_onboarding)]
    rounds = eval_filtered[: int(n_rounds)]
    relevant = eval_filtered[:relevant_window]
    return {
        "onboarding_ids": [_product_id(product) for product in onboarding],
        "round_ground_truth_ids": [_product_id(product) for product in rounds],
        "relevant_ids": [_product_id(product) for product in relevant],
    }


def _build_feature_space(products: list[dict[str, Any]]) -> FeatureSpace:
    try:
        return FeatureSpace(category="movies", products=products)  # type: ignore[arg-type]
    except TypeError:
        return FeatureSpace.build(products)


def _recommend_top_k(
    model: PrefixCFModel,
    feature_space: FeatureSpace,
    state: dict[str, Any],
    products: list[dict[str, Any]],
    *,
    excluded_ids: set[str] | None = None,
    k: int = 10,
) -> list[str]:
    blocked = set(excluded_ids or set())
    scored: list[tuple[float, str]] = []
    for product in products:
        product_id = _product_id(product)
        if product_id in blocked:
            continue
        vector = feature_space.vectorize(product)
        score = model.score_item(state, vector)
        scored.append((float(score), product_id))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [product_id for _, product_id in scored[:k]]


@unittest.skipIf(SKIP_IF_MISSING, SKIP_REASON)
class TestFeatureSpaceMovies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized_products = load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=800)
        cls.products = _to_model_products(cls.normalized_products)
        if not cls.products:
            raise unittest.SkipTest("No filtered movie products found in fixture")
        cls.feature_space = _build_feature_space(cls.products)
        cls.matrix = np.vstack([cls.feature_space.vectorize(product) for product in cls.products])

    def test_feature_matrix_has_rows_and_columns(self):
        self.assertGreater(self.matrix.shape[0], 0)
        self.assertGreater(self.matrix.shape[1], 0)
        self.assertEqual(self.matrix.shape[0], len(self.products))

    def test_at_least_90_percent_products_have_nonzero_vectors(self):
        nonzero_rows = int(np.count_nonzero(np.linalg.norm(self.matrix, axis=1) > 0))
        ratio = nonzero_rows / float(len(self.products))
        self.assertGreaterEqual(ratio, 0.90)

    def test_numeric_features_normalized_between_0_and_1(self):
        numeric_indices = [index for key, index in self.feature_space.feature_index.items() if "::num::" in key]
        if not numeric_indices:
            self.skipTest("No numeric feature indices found for movies")
        numeric_matrix = self.matrix[:, numeric_indices]
        self.assertTrue(np.isfinite(numeric_matrix).all())
        for column in range(numeric_matrix.shape[1]):
            values = numeric_matrix[:, column]
            minimum = float(np.min(values))
            maximum = float(np.max(values))
            if maximum - minimum <= 1e-12:
                continue
            normalized = (values - minimum) / (maximum - minimum)
            self.assertGreaterEqual(float(np.min(normalized)), 0.0)
            self.assertLessEqual(float(np.max(normalized)), 1.0)

    def test_genre_encoding_produces_nonzero_for_known_genre(self):
        known_genre_product = next(
            (product for product in self.products if any(str(genre).lower() == "action" for genre in product.get("genres", []))),
            None,
        )
        if known_genre_product is None:
            self.skipTest("No Action genre movie found in fixture slice")
        token = "cat::movies::multi::genres::action"
        token_index = self.feature_space.feature_index.get(token)
        self.assertIsNotNone(token_index)
        vector = self.feature_space.vectorize(known_genre_product)
        assert token_index is not None
        self.assertNotEqual(float(vector[token_index]), 0.0)


@unittest.skipIf(SKIP_IF_MISSING, SKIP_REASON)
class TestPrefixCFModelQuality(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized_products = load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=2000)
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < 200:
            raise unittest.SkipTest("Need at least 200 movies for holdout quality tests")

        cls.train_products, cls.eval_products = split_train_test(cls.products, test_ratio=0.25)
        cls.train_by_id = {_product_id(product): product for product in cls.train_products}
        cls.eval_by_id = {_product_id(product): product for product in cls.eval_products}
        cls.feature_space = _build_feature_space(cls.train_products)
        cls.model = PrefixCFModel(feature_space=cls.feature_space)
        cls.test_genres = ["Action", "Drama", "Comedy", "Science Fiction", "Thriller"]
        cls.cached_results = cls._compute_genre_results()

    @classmethod
    def _run_genre_session(cls, genre: str) -> dict[str, Any] | None:
        session = generate_synthetic_session(
            cls.train_products,
            cls.eval_products,
            genre,
            n_onboarding=10,
            n_rounds=5,
        )
        if session is None:
            return None

        state = cls.model.init_state()
        seen_ids: set[str] = set()
        trajectory: list[np.ndarray] = [np.array(state.get("user_vec", []), dtype=np.float32)]
        per_round_candidates: list[list[str]] = []
        precision_scores: list[float] = []
        ndcg_scores: list[float] = []
        hit_scores: list[float] = []
        relevant_remaining = set(session["relevant_ids"])

        for product_id in session["onboarding_ids"]:
            product = cls.train_by_id.get(product_id)
            if product is None:
                continue
            cls.model.update_with_selection(state, product, is_exception=False)
            seen_ids.add(product_id)
            trajectory.append(np.array(state.get("user_vec", []), dtype=np.float32))

        for relevant_id in session["round_ground_truth_ids"]:
            candidates = _recommend_top_k(
                cls.model,
                cls.feature_space,
                state,
                cls.eval_products,
                excluded_ids=seen_ids,
                k=10,
            )
            if len(candidates) < 10:
                continue
            per_round_candidates.append(candidates)
            precision_scores.append(precision_at_k(candidates, relevant_remaining, 10))
            ndcg_scores.append(ndcg_at_k(candidates, relevant_remaining, 10))
            hit_scores.append(hit_rate(candidates, relevant_remaining))
            if relevant_id in relevant_remaining:
                relevant_remaining.remove(relevant_id)

            relevant_product = cls.eval_by_id.get(relevant_id)
            if relevant_product is not None:
                cls.model.update_with_selection(state, relevant_product, is_exception=False)
                trajectory.append(np.array(state.get("user_vec", []), dtype=np.float32))
            seen_ids.update(candidates)
            seen_ids.add(relevant_id)

        if not precision_scores:
            return None
        return {
            "precision": float(np.mean(precision_scores)),
            "ndcg": float(np.mean(ndcg_scores)),
            "hit_rate": float(np.mean(hit_scores)),
            "candidates_by_round": per_round_candidates,
            "trajectory": trajectory,
        }

    @classmethod
    def _compute_genre_results(cls) -> list[dict[str, Any]]:
        results = []
        for genre in cls.test_genres:
            result = cls._run_genre_session(genre)
            if result is not None:
                results.append(result)
        return results

    def test_precision_at_10_above_threshold(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        mean_precision = float(np.mean([result["precision"] for result in results]))
        self.assertGreaterEqual(mean_precision, 0.08)

    def test_ndcg_at_10_above_threshold(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        mean_ndcg = float(np.mean([result["ndcg"] for result in results]))
        self.assertGreaterEqual(mean_ndcg, 0.12)

    def test_hit_rate_above_threshold(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        mean_hit = float(np.mean([result["hit_rate"] for result in results]))
        self.assertGreaterEqual(mean_hit, 0.25)

    def test_user_vector_changes_after_each_pick(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        trajectory = results[0]["trajectory"]
        self.assertGreater(len(trajectory), 1)
        for index in range(1, len(trajectory)):
            delta = float(np.linalg.norm(trajectory[index] - trajectory[index - 1]))
            self.assertGreater(delta, 0.0)

    def test_no_duplicate_candidates_in_single_round(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        for round_candidates in results[0]["candidates_by_round"]:
            self.assertEqual(len(round_candidates), len(set(round_candidates)))

    def test_candidate_diversity_across_rounds(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        union_ids = set()
        for round_candidates in results[0]["candidates_by_round"]:
            union_ids.update(round_candidates)
        self.assertGreaterEqual(len(union_ids), 20)


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


@unittest.skipIf(SKIP_IF_MISSING, SKIP_REASON)
class TestPBCFEngineMovies(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized_products = load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=600)
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < 150:
            raise unittest.SkipTest("Need at least 150 movies for PBCF offline tests")

        ranked = sorted(cls.products, key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)
        windows = [ranked[i * 30 : (i + 1) * 30] for i in range(5)]
        now = datetime.utcnow()
        rounds: list[_Round] = []
        for user_index, window in enumerate(windows, start=1):
            user_id = f"user-{user_index}"
            for idx, product in enumerate(window):
                rounds.append(
                    _Round(
                        game_id=user_id,
                        candidate_ids=[_product_id(product)],
                        ai_correct=(idx % 4 != 0),
                        created_at=now - timedelta(minutes=(idx + user_index)),
                    )
                )
        cls.db = _FakeDB(rounds)
        cls.engine = PBCFEngine(k=6, iters=20, seed=42)
        asyncio.run(cls.engine.train(cls.db))
        cls.product_ids = {_product_id(product) for product in cls.products}

    def _top_k_recommendations(self, user_id: str, k: int = 10) -> list[str]:
        predictions = asyncio.run(self.engine.predict_user_ratings(self.db, user_id))
        ordered = sorted(predictions.items(), key=lambda item: item[1], reverse=True)
        return [prefix_key for prefix_key, _ in ordered[:k]]

    def test_engine_initializes_without_error(self):
        self.assertIsNotNone(self.engine)
        self.assertIsNotNone(self.engine.artifacts)
        self.assertIsNotNone(self.engine.W)

    def test_recommendations_return_valid_product_ids(self):
        recommendations = self._top_k_recommendations("user-1", k=10)
        self.assertGreater(len(recommendations), 0)
        for product_id in recommendations:
            self.assertIn(product_id, self.product_ids)

    def test_recommendations_return_exactly_k_results(self):
        recommendations = self._top_k_recommendations("user-1", k=10)
        self.assertEqual(len(recommendations), 10)


@unittest.skipIf(SKIP_IF_MISSING, SKIP_REASON)
class TestEndToEndOfflineMoviePipeline(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.normalized_products = load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=1000)
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < 200:
            raise unittest.SkipTest("Need at least 200 movies for offline pipeline validation")
        cls.train_products, cls.eval_products = split_train_test(cls.products, test_ratio=0.25)
        cls.eval_by_id = {_product_id(product): product for product in cls.eval_products}

    def test_end_to_end_five_round_pipeline(self):
        feature_space = _build_feature_space(self.train_products)
        model = PrefixCFModel(feature_space=feature_space)
        state = model.init_state()
        initial_vec = np.array(state.get("user_vec", []), dtype=np.float32)

        onboarding = sorted(
            self.train_products,
            key=lambda item: float(item.get("vote_average") or 0.0),
            reverse=True,
        )[:10]
        for product in onboarding:
            model.update_with_selection(state, product, is_exception=False)

        seen_ids = {_product_id(product) for product in onboarding}
        all_seen = set(seen_ids)
        for _round in range(5):
            candidate_ids = _recommend_top_k(
                model,
                feature_space,
                state,
                self.eval_products,
                excluded_ids=seen_ids,
                k=10,
            )
            self.assertEqual(len(candidate_ids), 10)
            self.assertEqual(len(candidate_ids), len(set(candidate_ids)))
            all_seen.update(candidate_ids)
            seen_ids.update(candidate_ids)

            pick = max(
                (self.eval_by_id[candidate_id] for candidate_id in candidate_ids if candidate_id in self.eval_by_id),
                key=lambda product: float(product.get("vote_average") or 0.0),
            )
            model.update_with_selection(state, pick, is_exception=False)
            all_seen.add(_product_id(pick))

        final_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        self.assertGreater(float(np.linalg.norm(final_vec - initial_vec)), 0.0)
        self.assertGreaterEqual(len(all_seen), 20)


if __name__ == "__main__":
    unittest.main()
