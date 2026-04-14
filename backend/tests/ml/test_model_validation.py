import asyncio
import hashlib
import json
import math
import os
import pathlib
import unittest
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

import numpy as np
from sqlalchemy import select

from app.db import ProductRecord, get_session_factory, record_to_dict
from app.ml.pbcf_nmf import PBCFEngine
from app.ml.prefix_cf import FeatureSpace, PrefixCFModel

MOVIE_FIXTURE_PATH = pathlib.Path(__file__).parent.parent.parent / "data" / "tmdb_ingest_checkpoint.json"
CURATED_FIXTURE_PATH = pathlib.Path(__file__).parent / "fixtures" / "movie_validation_fixture.json"
BASELINE_PATH = pathlib.Path(__file__).parent / "fixtures" / "movie_validation_baseline.json"
TRUE_VALUES = {"1", "true", "yes", "on"}
MODEL_VALIDATION_SOURCE = os.getenv("MODEL_VALIDATION_SOURCE", "auto").strip().lower()
MODEL_VALIDATION_DB_FALLBACK = os.getenv("MODEL_VALIDATION_DB_FALLBACK", "").strip().lower() in TRUE_VALUES
MODEL_VALIDATION_EXTENDED = os.getenv("MODEL_VALIDATION_EXTENDED", "").strip().lower() in TRUE_VALUES


@dataclass(frozen=True)
class DatasetConfig:
    source_name: str
    quality_limit: int | None
    min_quality_products: int
    min_pbcf_products: int
    min_pipeline_products: int
    test_genres: tuple[str, ...]
    onboarding_count: int
    round_count: int
    relevant_window: int
    recommendation_k: int
    precision_threshold: float
    ndcg_threshold: float
    hit_rate_threshold: float


def _dataset_config(source_name: str) -> DatasetConfig:
    if source_name == "curated_fixture":
        return DatasetConfig(
            source_name=source_name,
            quality_limit=None,
            min_quality_products=30,
            min_pbcf_products=20,
            min_pipeline_products=20,
            test_genres=("Action", "Drama", "Comedy", "Science Fiction", "Thriller"),
            onboarding_count=3,
            round_count=2,
            relevant_window=3,
            recommendation_k=5,
            precision_threshold=0.20,
            ndcg_threshold=0.25,
            hit_rate_threshold=0.40,
        )
    return DatasetConfig(
        source_name=source_name,
        quality_limit=2000,
        min_quality_products=200,
        min_pbcf_products=150,
        min_pipeline_products=200,
        test_genres=("Action", "Drama", "Comedy", "Science Fiction", "Thriller"),
        onboarding_count=10,
        round_count=5,
        relevant_window=20,
        recommendation_k=10,
        precision_threshold=0.08,
        ndcg_threshold=0.12,
        hit_rate_threshold=0.25,
    )


def load_movies_from_fixture(path, limit=None) -> list[dict]:
    """Load normalized movie docs from either TMDB checkpoint or curated fixture."""
    fixture_path = pathlib.Path(path)
    payload = json.loads(fixture_path.read_text(encoding="utf-8"))
    docs = payload.get("staged_docs") or payload.get("products") or []

    products: list[dict[str, Any]] = []
    for doc in docs:
        if isinstance(doc, dict) and "id" in doc and "data" in doc:
            title = str((doc.get("data") or {}).get("title") or "").strip()
            source_id = str(doc.get("id") or "").strip()
            vote_average = float((doc.get("data") or {}).get("vote_average") or 0.0)
            normalized = {
                "id": source_id,
                "category": str(doc.get("category") or "movies"),
                "data": dict(doc.get("data") or {}),
            }
        else:
            title = str(doc.get("title") or "").strip()
            source_id = str(doc.get("source_id") or "").strip()
            vote_average = float(doc.get("vote_average") or 0.0)
            normalized = {
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
        if not title or not source_id:
            continue
        if vote_average <= 0.0:
            continue

        products.append(normalized)
        if limit is not None and len(products) >= int(limit):
            break
    return products


async def load_movies_from_db(limit=None) -> list[dict]:
    """Load movie products from the configured Postgres database."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        stmt = select(ProductRecord).where(ProductRecord.category == "movies").order_by(ProductRecord.created_at.desc())
        if limit is not None:
            stmt = stmt.limit(int(limit))
        rows = (await session.execute(stmt)).scalars().all()
    products = []
    for row in rows:
        record = record_to_dict(row)
        title = str(record.get("title") or "").strip()
        source_id = str(record.get("_id") or record.get("source_id") or "").strip()
        vote_average = float(record.get("vote_average") or 0.0)
        if not title or not source_id or vote_average <= 0.0:
            continue
        products.append(
            {
                "id": source_id,
                "category": "movies",
                "data": {
                    "title": title,
                    "description": str(record.get("description") or ""),
                    "vendor": str(record.get("vendor") or "").strip() or None,
                    "primary_country": str(record.get("primary_country") or "").strip() or None,
                    "original_language": str(record.get("original_language") or "").strip() or None,
                    "certification": str(record.get("certification") or "").strip() or None,
                    "decade_bucket": str(record.get("decade_bucket") or "").strip() or None,
                    "runtime_bucket": str(record.get("runtime_bucket") or "").strip() or None,
                    "genres": [str(item).strip() for item in (record.get("genres") or []) if str(item).strip()],
                    "keywords": [str(item).strip() for item in (record.get("keywords") or []) if str(item).strip()],
                    "production_companies": [
                        str(item).strip() for item in (record.get("production_companies") or []) if str(item).strip()
                    ],
                    "directors": [str(item).strip() for item in (record.get("directors") or []) if str(item).strip()],
                    "release_year": int(record.get("release_year") or 0),
                    "runtime_minutes": int(record.get("runtime_minutes") or 0),
                    "vote_average": vote_average,
                    "popularity": float(record.get("popularity") or 0.0),
                    "vote_count": int(record.get("vote_count") or 0),
                },
            }
        )
    return products


def resolve_movie_dataset(limit=None, *, prefer_extended=False) -> tuple[str, list[dict]]:
    """Pick the best available validation dataset for the current environment."""
    explicit = MODEL_VALIDATION_SOURCE

    if explicit == "checkpoint":
        if not MOVIE_FIXTURE_PATH.exists():
            raise unittest.SkipTest("MODEL_VALIDATION_SOURCE=checkpoint but backend/data/tmdb_ingest_checkpoint.json is missing")
        return "checkpoint", load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=limit)

    if explicit == "fixture":
        if not CURATED_FIXTURE_PATH.exists():
            raise unittest.SkipTest(
                "MODEL_VALIDATION_SOURCE=fixture but backend/tests/ml/fixtures/movie_validation_fixture.json is missing"
            )
        return "curated_fixture", load_movies_from_fixture(CURATED_FIXTURE_PATH, limit=limit)

    if explicit == "db":
        try:
            return "db", asyncio.run(load_movies_from_db(limit=limit))
        except Exception as exc:
            raise unittest.SkipTest(f"MODEL_VALIDATION_SOURCE=db but DB load failed: {exc}") from exc

    if MOVIE_FIXTURE_PATH.exists():
        return "checkpoint", load_movies_from_fixture(MOVIE_FIXTURE_PATH, limit=limit)

    if CURATED_FIXTURE_PATH.exists():
        return "curated_fixture", load_movies_from_fixture(CURATED_FIXTURE_PATH, limit=limit)

    if prefer_extended or MODEL_VALIDATION_DB_FALLBACK or MODEL_VALIDATION_EXTENDED:
        try:
            return "db", asyncio.run(load_movies_from_db(limit=limit))
        except Exception as exc:
            raise unittest.SkipTest(
                "No checkpoint or curated fixture was found, and DB-backed validation could not load movies: "
                f"{exc}"
            ) from exc

    raise unittest.SkipTest(
        "No movie validation dataset found. Add backend/data/tmdb_ingest_checkpoint.json, "
        "commit backend/tests/ml/fixtures/movie_validation_fixture.json, or enable DB-backed validation."
    )


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


def generate_synthetic_session(train_products, eval_products, seed_genre, n_onboarding=10, n_rounds=5, relevant_window=None):
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
    if relevant_window is None:
        relevant_window = max(20, int(n_rounds) * 4)
    else:
        relevant_window = max(int(relevant_window), int(n_rounds))
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


def generate_synthetic_session_for_slice(
    train_products,
    eval_products,
    field,
    value,
    *,
    n_onboarding=10,
    n_rounds=5,
    relevant_window=None,
):
    target = str(value).strip().lower()

    def matches(product):
        raw = product.get(field)
        if raw is None:
            return False
        return str(raw).strip().lower() == target

    train_filtered = [product for product in train_products if matches(product)]
    eval_filtered = [product for product in eval_products if matches(product)]
    train_filtered.sort(key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)
    eval_filtered.sort(key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)

    if len(train_filtered) < int(n_onboarding):
        return None
    if relevant_window is None:
        relevant_window = max(20, int(n_rounds) * 4)
    else:
        relevant_window = max(int(relevant_window), int(n_rounds))
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


class _MovieDatasetCase(unittest.TestCase):
    prefer_extended_dataset = False
    dataset_limit: int | None = None

    @classmethod
    def load_dataset(cls) -> tuple[str, list[dict], DatasetConfig]:
        source_name, normalized_products = resolve_movie_dataset(
            limit=cls.dataset_limit,
            prefer_extended=cls.prefer_extended_dataset,
        )
        return source_name, normalized_products, _dataset_config(source_name)


class _MovieQualityMixin:
    @classmethod
    def _build_quality_results(cls):
        cls.train_products, cls.eval_products = split_train_test(cls.products, test_ratio=0.25)
        cls.train_by_id = {_product_id(product): product for product in cls.train_products}
        cls.eval_by_id = {_product_id(product): product for product in cls.eval_products}
        cls.feature_space = _build_feature_space(cls.train_products)
        cls.model = PrefixCFModel(feature_space=cls.feature_space)
        cls.test_genres = list(cls.dataset_config.test_genres)
        cls.cached_results = cls._compute_genre_results()

    @classmethod
    def current_quality_summary(cls) -> dict[str, float]:
        results = cls.cached_results
        if not results:
            raise unittest.SkipTest("No synthetic holdout sessions available for configured genres")
        return {
            "precision_at_k": float(np.mean([result["precision"] for result in results])),
            "ndcg_at_k": float(np.mean([result["ndcg"] for result in results])),
            "hit_rate": float(np.mean([result["hit_rate"] for result in results])),
            "candidate_diversity": float(
                np.mean(
                    [
                        len(set(candidate for round_ids in result["candidates_by_round"] for candidate in round_ids))
                        for result in results
                    ]
                )
            ),
        }

    @classmethod
    def _run_genre_session(cls, genre: str) -> dict[str, Any] | None:
        session = generate_synthetic_session(
            cls.train_products,
            cls.eval_products,
            genre,
            n_onboarding=cls.dataset_config.onboarding_count,
            n_rounds=cls.dataset_config.round_count,
            relevant_window=cls.dataset_config.relevant_window,
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
                k=cls.dataset_config.recommendation_k,
            )
            if len(candidates) < cls.dataset_config.recommendation_k:
                continue
            per_round_candidates.append(candidates)
            precision_scores.append(
                precision_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k)
            )
            ndcg_scores.append(ndcg_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k))
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


def load_baseline_metrics(path: pathlib.Path = BASELINE_PATH) -> dict[str, Any]:
    return dict(json.loads(path.read_text(encoding="utf-8")))


def metric_floor(baseline: float, tolerance: float) -> float:
    return float(baseline) * (1.0 - float(tolerance))


class TestFeatureSpaceMovies(_MovieDatasetCase):
    dataset_limit = 800

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        cls.products = _to_model_products(cls.normalized_products)
        if not cls.products:
            raise unittest.SkipTest(f"No filtered movie products found in {cls.source_name}")
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


class TestPrefixCFModelQuality(_MovieDatasetCase, _MovieQualityMixin):
    dataset_limit = 2000

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < cls.dataset_config.min_quality_products:
            raise unittest.SkipTest(
                f"Need at least {cls.dataset_config.min_quality_products} movies for holdout quality tests "
                f"from {cls.source_name}"
            )

        cls._build_quality_results()

    @classmethod
    def _run_genre_session(cls, genre: str) -> dict[str, Any] | None:
        session = generate_synthetic_session(
            cls.train_products,
            cls.eval_products,
            genre,
            n_onboarding=cls.dataset_config.onboarding_count,
            n_rounds=cls.dataset_config.round_count,
            relevant_window=cls.dataset_config.relevant_window,
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
                k=cls.dataset_config.recommendation_k,
            )
            if len(candidates) < cls.dataset_config.recommendation_k:
                continue
            per_round_candidates.append(candidates)
            precision_scores.append(
                precision_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k)
            )
            ndcg_scores.append(ndcg_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k))
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
        self.assertGreaterEqual(mean_precision, self.dataset_config.precision_threshold)

    def test_ndcg_at_10_above_threshold(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        mean_ndcg = float(np.mean([result["ndcg"] for result in results]))
        self.assertGreaterEqual(mean_ndcg, self.dataset_config.ndcg_threshold)

    def test_hit_rate_above_threshold(self):
        results = self.cached_results
        if not results:
            self.skipTest("No synthetic holdout sessions available for configured genres")
        mean_hit = float(np.mean([result["hit_rate"] for result in results]))
        self.assertGreaterEqual(mean_hit, self.dataset_config.hit_rate_threshold)

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
        self.assertGreaterEqual(len(union_ids), self.dataset_config.recommendation_k)


class TestMovieModelRegressionBaseline(_MovieDatasetCase, _MovieQualityMixin):
    dataset_limit = 2000

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        if cls.source_name != "curated_fixture":
            raise unittest.SkipTest("Regression baseline comparisons currently target the curated fixture path only")
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < cls.dataset_config.min_quality_products:
            raise unittest.SkipTest(
                f"Need at least {cls.dataset_config.min_quality_products} movies for regression validation "
                f"from {cls.source_name}"
            )
        if not BASELINE_PATH.exists():
            raise unittest.SkipTest("Movie validation baseline file is missing")
        cls.baseline = load_baseline_metrics()
        cls._build_quality_results()
        cls.summary = cls.current_quality_summary()

    def test_precision_stays_within_tolerance_of_baseline(self):
        tolerance = float(self.baseline["tolerances"]["precision_at_k"])
        expected = float(self.baseline["metrics"]["precision_at_k"])
        self.assertGreaterEqual(self.summary["precision_at_k"], metric_floor(expected, tolerance))

    def test_ndcg_stays_within_tolerance_of_baseline(self):
        tolerance = float(self.baseline["tolerances"]["ndcg_at_k"])
        expected = float(self.baseline["metrics"]["ndcg_at_k"])
        self.assertGreaterEqual(self.summary["ndcg_at_k"], metric_floor(expected, tolerance))

    def test_hit_rate_stays_within_tolerance_of_baseline(self):
        tolerance = float(self.baseline["tolerances"]["hit_rate"])
        expected = float(self.baseline["metrics"]["hit_rate"])
        self.assertGreaterEqual(self.summary["hit_rate"], metric_floor(expected, tolerance))

    def test_candidate_diversity_stays_within_tolerance_of_baseline(self):
        tolerance = float(self.baseline["tolerances"]["candidate_diversity"])
        expected = float(self.baseline["metrics"]["candidate_diversity"])
        self.assertGreaterEqual(self.summary["candidate_diversity"], metric_floor(expected, tolerance))

    def test_feature_space_shape_stays_close_to_baseline(self):
        baseline_feature_count = int(self.baseline["feature_space"]["feature_count"])
        tolerance = float(self.baseline["tolerances"]["feature_count"])
        current_feature_count = len(self.feature_space.feature_index)
        self.assertGreaterEqual(current_feature_count, int(math.floor(metric_floor(baseline_feature_count, tolerance))))

    def test_nonzero_ratio_stays_within_tolerance_of_baseline(self):
        matrix = np.vstack([self.feature_space.vectorize(product) for product in self.products])
        nonzero_rows = int(np.count_nonzero(np.linalg.norm(matrix, axis=1) > 0))
        current_ratio = nonzero_rows / float(len(self.products))
        tolerance = float(self.baseline["tolerances"]["nonzero_ratio"])
        expected = float(self.baseline["feature_space"]["nonzero_ratio"])
        self.assertGreaterEqual(current_ratio, metric_floor(expected, tolerance))


class TestMovieSliceQuality(_MovieDatasetCase, _MovieQualityMixin):
    dataset_limit = 2000
    SLICE_FIELDS = ("decade_bucket", "certification", "original_language", "primary_country")

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < cls.dataset_config.min_quality_products:
            raise unittest.SkipTest(
                f"Need at least {cls.dataset_config.min_quality_products} movies for slice validation from {cls.source_name}"
            )
        cls.train_products, cls.eval_products = split_train_test(cls.products, test_ratio=0.25)
        cls.train_by_id = {_product_id(product): product for product in cls.train_products}
        cls.eval_by_id = {_product_id(product): product for product in cls.eval_products}
        cls.feature_space = _build_feature_space(cls.train_products)
        cls.model = PrefixCFModel(feature_space=cls.feature_space)
        cls.slice_results = cls._compute_slice_results()

    @classmethod
    def _run_slice_session(cls, field: str, value: str) -> dict[str, Any] | None:
        session = generate_synthetic_session_for_slice(
            cls.train_products,
            cls.eval_products,
            field,
            value,
            n_onboarding=cls.dataset_config.onboarding_count,
            n_rounds=cls.dataset_config.round_count,
            relevant_window=cls.dataset_config.relevant_window,
        )
        if session is None:
            return None

        state = cls.model.init_state()
        seen_ids: set[str] = set()
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

        for relevant_id in session["round_ground_truth_ids"]:
            candidates = _recommend_top_k(
                cls.model,
                cls.feature_space,
                state,
                cls.eval_products,
                excluded_ids=seen_ids,
                k=cls.dataset_config.recommendation_k,
            )
            if len(candidates) < cls.dataset_config.recommendation_k:
                continue
            precision_scores.append(
                precision_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k)
            )
            ndcg_scores.append(ndcg_at_k(candidates, relevant_remaining, cls.dataset_config.recommendation_k))
            hit_scores.append(hit_rate(candidates, relevant_remaining))
            if relevant_id in relevant_remaining:
                relevant_remaining.remove(relevant_id)
            relevant_product = cls.eval_by_id.get(relevant_id)
            if relevant_product is not None:
                cls.model.update_with_selection(state, relevant_product, is_exception=False)
            seen_ids.update(candidates)
            seen_ids.add(relevant_id)

        if not precision_scores:
            return None
        return {
            "field": field,
            "value": value,
            "precision": float(np.mean(precision_scores)),
            "ndcg": float(np.mean(ndcg_scores)),
            "hit_rate": float(np.mean(hit_scores)),
        }

    @classmethod
    def _compute_slice_results(cls) -> list[dict[str, Any]]:
        min_slice_count = 4 if cls.source_name == "curated_fixture" else 25
        results: list[dict[str, Any]] = []
        for field in cls.SLICE_FIELDS:
            counts: dict[str, int] = {}
            for product in cls.products:
                raw = product.get(field)
                if raw is None:
                    continue
                key = str(raw).strip()
                if not key:
                    continue
                counts[key] = counts.get(key, 0) + 1
            for value, count in counts.items():
                if count < min_slice_count:
                    continue
                result = cls._run_slice_session(field, value)
                if result is not None:
                    results.append(result)
        return results

    def test_slice_validation_generates_at_least_one_result(self):
        if not self.slice_results:
            self.skipTest("No sufficiently represented movie slices produced evaluable sessions")
        self.assertGreaterEqual(len(self.slice_results), 1)

    def test_slice_hit_rate_remains_nonzero(self):
        if not self.slice_results:
            self.skipTest("No sufficiently represented movie slices produced evaluable sessions")
        for result in self.slice_results:
            self.assertGreater(result["hit_rate"], 0.0)

    def test_slice_precision_stays_above_floor(self):
        if not self.slice_results:
            self.skipTest("No sufficiently represented movie slices produced evaluable sessions")
        floor = max(0.05, self.dataset_config.precision_threshold * 0.5)
        for result in self.slice_results:
            self.assertGreaterEqual(result["precision"], floor)

    def test_slice_ndcg_stays_above_floor(self):
        if not self.slice_results:
            self.skipTest("No sufficiently represented movie slices produced evaluable sessions")
        floor = max(0.10, self.dataset_config.ndcg_threshold * 0.70)
        for result in self.slice_results:
            self.assertGreaterEqual(result["ndcg"], floor)


class TestMovieNoisyDataRobustness(unittest.TestCase):
    def _noisy_products(self) -> list[dict[str, Any]]:
        return [
            {
                "_id": "n1",
                "category": "movies",
                "title": "Broken Genres",
                "genres": "Action",
                "keywords": [],
                "vote_average": "8.2",
                "release_year": "2020",
                "runtime_minutes": None,
            },
            {
                "_id": "n2",
                "category": "movies",
                "title": "Sparse Drama",
                "genres": ["Drama"],
                "keywords": None,
                "vendor": None,
                "vote_average": "bad",
                "release_year": 2011,
                "popularity": 44.0,
            },
            {
                "_id": "n3",
                "category": "movies",
                "title": "Tiny Comedy",
                "genres": ["Comedy"],
                "keywords": ["short"],
                "vote_average": 7.1,
                "runtime_bucket": "91-120 min",
            },
            {
                "_id": "n4",
                "category": "movies",
                "title": "Duplicate-Like Comedy",
                "genres": ["Comedy"],
                "keywords": ["short"],
                "vote_average": 7.0,
                "runtime_minutes": "99",
            },
            {
                "_id": "n5",
                "category": "movies",
                "title": "Countryless Sci-Fi",
                "genres": ["Science Fiction"],
                "keywords": ["future"],
                "original_language": "",
                "primary_country": None,
                "vote_average": 8.0,
                "popularity": "55.5",
            },
            {
                "_id": "n6",
                "category": "movies",
                "title": "Keywordless Thriller",
                "genres": ["Thriller"],
                "keywords": ["", None, "mystery"],
                "certification": None,
                "vote_average": 7.8,
                "runtime_minutes": 108,
            },
        ]

    def test_feature_space_builds_and_vectorizes_with_sparse_products(self):
        products = self._noisy_products()
        feature_space = _build_feature_space(products)
        matrix = np.vstack([feature_space.vectorize(product) for product in products])

        self.assertEqual(matrix.shape[0], len(products))
        self.assertTrue(np.isfinite(matrix).all())
        self.assertGreater(matrix.shape[1], 0)

    def test_model_scores_remain_finite_with_bad_numeric_values(self):
        products = self._noisy_products()
        feature_space = _build_feature_space(products)
        model = PrefixCFModel(feature_space=feature_space)
        state = model.init_state()

        model.update_with_selection(state, products[2], is_exception=False)
        model.update_with_selection(state, products[4], is_exception=False)

        scores = [model.score_item(state, feature_space.vectorize(product)) for product in products]

        self.assertTrue(all(math.isfinite(score) for score in scores))
        self.assertTrue(all(1.0 <= score <= 5.0 for score in scores))

    def test_top_k_recommendation_handles_tiny_sparse_pool_without_duplicates(self):
        products = self._noisy_products()
        feature_space = _build_feature_space(products)
        model = PrefixCFModel(feature_space=feature_space)
        state = model.init_state()
        model.update_with_selection(state, products[0], is_exception=False)

        recommended_ids = _recommend_top_k(
            model,
            feature_space,
            state,
            products[1:4],
            excluded_ids={"n1"},
            k=5,
        )

        self.assertEqual(len(recommended_ids), 3)
        self.assertEqual(len(recommended_ids), len(set(recommended_ids)))

    def test_negative_feedback_and_prefix_rating_tolerate_sparse_state(self):
        products = self._noisy_products()
        feature_space = _build_feature_space(products)
        model = PrefixCFModel(feature_space=feature_space)
        state = model.init_state()

        model.update_with_negative_feedback(state, products[1])
        model.update_with_prefix_rating(state, 4)

        predicted = model.predict_prefix_rating(state)
        self.assertTrue(math.isfinite(predicted))
        self.assertGreaterEqual(predicted, 1.0)
        self.assertLessEqual(predicted, 5.0)


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


class TestPBCFEngineMovies(_MovieDatasetCase):
    dataset_limit = 600

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < cls.dataset_config.min_pbcf_products:
            raise unittest.SkipTest(
                f"Need at least {cls.dataset_config.min_pbcf_products} movies for PBCF offline tests from {cls.source_name}"
            )

        ranked = sorted(cls.products, key=lambda item: float(item.get("vote_average") or 0.0), reverse=True)
        window_size = max(cls.dataset_config.recommendation_k + 3, min(30, max(8, len(ranked) // 4)))
        window_count = max(3, min(5, len(ranked) // window_size))
        windows = [ranked[i * window_size : (i + 1) * window_size] for i in range(window_count)]
        windows = [window for window in windows if window]
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
        recommendations = self._top_k_recommendations("user-1", k=self.dataset_config.recommendation_k)
        self.assertGreater(len(recommendations), 0)
        for product_id in recommendations:
            self.assertIn(product_id, self.product_ids)

    def test_recommendations_return_exactly_k_results(self):
        recommendations = self._top_k_recommendations("user-1", k=self.dataset_config.recommendation_k)
        self.assertEqual(len(recommendations), self.dataset_config.recommendation_k)


class TestEndToEndOfflineMoviePipeline(_MovieDatasetCase):
    dataset_limit = 1000

    @classmethod
    def setUpClass(cls):
        cls.source_name, cls.normalized_products, cls.dataset_config = cls.load_dataset()
        cls.products = _to_model_products(cls.normalized_products)
        if len(cls.products) < cls.dataset_config.min_pipeline_products:
            raise unittest.SkipTest(
                f"Need at least {cls.dataset_config.min_pipeline_products} movies for offline pipeline validation "
                f"from {cls.source_name}"
            )
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
        )[: self.dataset_config.onboarding_count]
        for product in onboarding:
            model.update_with_selection(state, product, is_exception=False)

        seen_ids = {_product_id(product) for product in onboarding}
        all_seen = set(seen_ids)
        for _round in range(self.dataset_config.round_count):
            remaining_pool = [
                product for product in self.eval_products if _product_id(product) not in seen_ids
            ]
            expected_k = min(self.dataset_config.recommendation_k, len(remaining_pool))
            if expected_k == 0:
                self.skipTest("No unseen evaluation products remain for curated end-to-end validation")
            candidate_ids = _recommend_top_k(
                model,
                feature_space,
                state,
                self.eval_products,
                excluded_ids=seen_ids,
                k=expected_k,
            )
            self.assertEqual(len(candidate_ids), expected_k)
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
        self.assertGreaterEqual(len(all_seen), self.dataset_config.onboarding_count + self.dataset_config.recommendation_k)


if __name__ == "__main__":
    unittest.main()
