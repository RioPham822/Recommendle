from __future__ import annotations

import math
from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Iterable

import numpy as np

from ..category_profiles import (
    DEFAULT_CATEGORY,
    extract_feature_tokens,
    is_numeric_feature_key,
)
from ..models import Product


@dataclass
class FeatureSpace:
    feature_index: dict[str, int]
    numeric_stats: dict[str, tuple[float, float]]

    @staticmethod
    def _category_of(product: Any) -> str:
        if isinstance(product, dict):
            value = product.get("category")
        else:
            value = getattr(product, "category", None)
        if not value:
            return DEFAULT_CATEGORY
        return str(value).strip().lower()

    @classmethod
    def build(cls, products: Iterable[Product]) -> "FeatureSpace":
        feature_index: dict[str, int] = {}
        numeric_values: dict[str, list[float]] = defaultdict(list)

        def add_feature(name: str):
            if name not in feature_index:
                feature_index[name] = len(feature_index)

        for product in products:
            category = cls._category_of(product)
            tokens, nums = extract_feature_tokens(product, category)
            for token in tokens:
                add_feature(token)
            for numeric_key, value in nums.items():
                add_feature(numeric_key)
                numeric_values[numeric_key].append(value)

        stats: dict[str, tuple[float, float]] = {}
        for numeric_key, values in numeric_values.items():
            mean = float(np.mean(values)) if values else 0.0
            std = float(np.std(values)) if values else 1.0
            if std == 0:
                std = 1.0
            stats[numeric_key] = (mean, std)

        return cls(feature_index=feature_index, numeric_stats=stats)

    def vectorize(self, product: Any) -> np.ndarray:
        """Vectorize a product document from MongoDB-backed models."""
        vec = np.zeros(len(self.feature_index), dtype=np.float32)

        def set_feature(name: str, value: float = 1.0):
            idx = self.feature_index.get(name)
            if idx is not None:
                vec[idx] = value

        category = self._category_of(product)
        tokens, nums = extract_feature_tokens(product, category)
        for token in tokens:
            set_feature(token, 1.0)

        for numeric_key, raw_value in nums.items():
            mean, std = self.numeric_stats.get(numeric_key, (0.0, 1.0))
            z = (float(raw_value) - mean) / std
            set_feature(numeric_key, float(z))

        return vec


class PrefixCFModel:
    def __init__(self, feature_space: FeatureSpace):
        self.feature_space = feature_space

    def init_state(self) -> dict:
        return {
            "user_vec": [0.0] * len(self.feature_space.feature_index),
            "bias": 0.0,
            "count": 0,
            "exception_weight": 0.35,
            "decay": 0.85,
        }

    def update_with_selection(self, state: dict, product: Product, is_exception: bool) -> None:
        vec = self.feature_space.vectorize(product)
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        decay = float(state.get("decay", 0.85))
        weight = float(state.get("exception_weight", 0.35) if is_exception else 1.0)
        updated = decay * user_vec + weight * vec
        state["user_vec"] = updated.tolist()
        state["count"] = int(state.get("count", 0)) + 1

    def update_with_prefix_rating(self, state: dict, rating: int) -> None:
        predicted = self.predict_prefix_rating(state)
        error = float(rating) - predicted
        state["bias"] = float(state.get("bias", 0.0)) + 0.25 * error

    def predict_prefix_rating(self, state: dict) -> float:
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        bias = float(state.get("bias", 0.0))
        norm = float(np.linalg.norm(user_vec))
        base = 3.0 + 1.5 * math.tanh(norm / 3.0) + bias
        return float(min(5.0, max(1.0, base)))

    def score_item(self, state: dict, item_vec: np.ndarray) -> float:
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        bias = float(state.get("bias", 0.0))
        denom = (np.linalg.norm(user_vec) * np.linalg.norm(item_vec))
        similarity = 0.0
        if denom > 0:
            similarity = float(np.dot(user_vec, item_vec) / denom)
        score = 3.0 + 1.7 * similarity + bias
        return float(min(5.0, max(1.0, score)))

    def coherence_score(self, item_vecs: list[np.ndarray]) -> float:
        if len(item_vecs) < 2:
            return 0.0
        total = 0.0
        count = 0
        for i in range(len(item_vecs)):
            for j in range(i + 1, len(item_vecs)):
                denom = np.linalg.norm(item_vecs[i]) * np.linalg.norm(item_vecs[j])
                if denom == 0:
                    continue
                total += float(np.dot(item_vecs[i], item_vecs[j]) / denom)
                count += 1
        if count == 0:
            return 0.0
        return float((total / count + 1.0) / 2.0)  # scale to 0..1

    # ── Hidden-preference discovery ──────────────────────────────

    # Tuning constants — adjust after play-testing
    HIDDEN_MIN_WEIGHT = 0.08       # user_vec weight must exceed this (normalised)
    HIDDEN_MIN_LATENCY = 0.05      # latency_score must exceed this
    HIDDEN_MIN_SELECTIONS = 2      # need at least this many picks before detecting

    def detect_hidden_preferences(
        self,
        state: dict,
        selected_products: list[Any],
        *,
        top_n: int = 6,
    ) -> list[dict]:
        """Identify features the user accumulated *incidentally* rather than intentionally.

        Returns a list of dicts:
            [{"feature": raw_key, "latency": float, "weight": float}, ...]
        sorted by latency score descending (most "hidden" first).
        """
        if state.get("count", 0) < self.HIDDEN_MIN_SELECTIONS or not selected_products:
            return []

        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        n_features = len(self.feature_space.feature_index)
        if n_features == 0:
            return []

        # 1. Normalise user_vec to 0-1 scale  (min-max over positive dims)
        abs_vec = np.abs(user_vec)
        max_val = float(abs_vec.max())
        if max_val == 0:
            return []
        pref_weight = abs_vec / max_val  # 0..1

        # 2. Build selection-frequency vector
        #    For each feature index, what fraction of selected products carry it?
        freq_vec = np.zeros(n_features, dtype=np.float32)
        for product in selected_products:
            pvec = self.feature_space.vectorize(product)
            freq_vec += (pvec != 0).astype(np.float32)
        n_sel = float(len(selected_products))
        freq_vec /= n_sel  # 0..1 — fraction of selections that have each feature

        # 3. Latency = preference weight − selection frequency
        #    High latency ⇒ the model learned this feature from co-occurrence,
        #    not because the user explicitly targeted it.
        latency = pref_weight - freq_vec

        # 4. Filter & rank
        inv_index = {v: k for k, v in self.feature_space.feature_index.items()}
        results: list[dict] = []
        for idx in range(n_features):
            pw = float(pref_weight[idx])
            ls = float(latency[idx])
            if pw < self.HIDDEN_MIN_WEIGHT or ls < self.HIDDEN_MIN_LATENCY:
                continue
            fname = inv_index.get(idx, "")
            # Numeric dimensions are noisy and not user-facing as hidden tags.
            if is_numeric_feature_key(fname):
                continue
            results.append({
                "feature": fname,
                "latency": round(ls, 4),
                "weight": round(pw, 4),
            })

        results.sort(key=lambda r: r["latency"], reverse=True)
        return results[:top_n]

    def get_hidden_gem_products(
        self,
        state: dict,
        selected_products: list[Any],
        all_products: list[Any],
        *,
        top_n: int = 5,
    ) -> list[tuple[float, Any, list[str]]]:
        """Find products the user would enjoy via *hidden* preferences only.

        Returns [(score, product_dict, [matched_hidden_feature_keys, ...]), ...]
        """
        hidden = self.detect_hidden_preferences(state, selected_products, top_n=10)
        if not hidden:
            return []

        # Build a mask that zeroes out everything except hidden-feature dims
        user_vec = np.array(state.get("user_vec", []), dtype=np.float32)
        mask = np.zeros_like(user_vec)
        hidden_indices: dict[int, str] = {}
        for h in hidden:
            idx = self.feature_space.feature_index.get(h["feature"])
            if idx is not None:
                mask[idx] = 1.0
                hidden_indices[idx] = h["feature"]

        hidden_vec = user_vec * mask
        hidden_norm = float(np.linalg.norm(hidden_vec))
        if hidden_norm == 0:
            return []

        # Exclude already-selected product IDs
        selected_ids = set()
        for p in selected_products:
            pid = str(p.get("_id", "")) if isinstance(p, dict) else str(getattr(p, "id", ""))
            if pid:
                selected_ids.add(pid)

        scored: list[tuple[float, Any, list[str]]] = []
        for product in all_products:
            pid = str(product.get("_id", "")) if isinstance(product, dict) else str(getattr(product, "id", ""))
            if pid in selected_ids:
                continue
            item_vec = self.feature_space.vectorize(product)
            item_norm = float(np.linalg.norm(item_vec))
            if item_norm == 0:
                continue
            sim = float(np.dot(hidden_vec, item_vec) / (hidden_norm * item_norm))
            # Which hidden features does this product match?
            matched = [
                hidden_indices[idx]
                for idx in hidden_indices
                if item_vec[idx] != 0
            ]
            if matched:
                scored.append((sim, product, matched))

        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[:top_n]
