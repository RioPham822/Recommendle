"""PBCF matrix-factorization engine used for prefix-rating personalization."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import numpy as np
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import GameRoundRecord


@dataclass
class PBCFArtifacts:
    """Training matrix artifacts and lookup indices."""

    prefix_keys: list[str]
    user_ids: list[str]
    ratings: np.ndarray
    mask: np.ndarray


class PBCFEngine:
    """Non-negative matrix factorization engine over prefix-user ratings."""

    def __init__(self, k: int = 6, iters: int = 50, seed: int = 42):
        """Initialize factorization hyperparameters and RNG."""
        self.k = k
        self.iters = iters
        self.rng = np.random.default_rng(seed)
        self.artifacts: PBCFArtifacts | None = None
        self.W: np.ndarray | None = None
        self.H: np.ndarray | None = None

    async def _build_prefix_from_game_round(self, game_round: dict[str, Any]) -> str | None:
        """Build stable prefix key from current round candidate product IDs."""
        candidate_ids = game_round.get("candidate_ids")
        if not candidate_ids or not isinstance(candidate_ids, list):
            return None
        sorted_candidates = sorted(str(cid) for cid in candidate_ids)
        return "-".join(sorted_candidates)

    async def build_matrix(self, db: AsyncSession) -> PBCFArtifacts | None:
        """Build sparse rating matrix from completed historical rounds."""
        rounds = (
            (
                await db.execute(
                    select(GameRoundRecord)
                    .where(GameRoundRecord.completed.is_(True))
                    .order_by(GameRoundRecord.created_at.asc())
                )
            )
            .scalars()
            .all()
        )
        if not rounds:
            return None

        latest: dict[tuple[str, str], tuple[datetime, int]] = {}
        for round_row in rounds:
            round_data = {
                "candidate_ids": getattr(round_row, "candidate_ids", None),
                "user_id": getattr(round_row, "game_id", None),
                "ai_correct": round_row.ai_correct,
                "created_at": round_row.created_at,
            }
            key = await self._build_prefix_from_game_round(round_data)
            if not key:
                continue
            user_id = round_data.get("user_id")
            if not user_id:
                continue
            is_correct = bool(round_data.get("ai_correct", False))
            rating_value = 5 if is_correct else 1
            stamp = round_data.get("created_at", datetime.utcnow())
            prev = latest.get((key, user_id))
            if prev is None or stamp > prev[0]:
                latest[(key, user_id)] = (stamp, rating_value)

        prefix_keys: list[str] = []
        user_ids: list[str] = []
        key_index: dict[str, int] = {}
        user_index: dict[str, int] = {}
        for key, user_id in latest.keys():
            if key not in key_index:
                key_index[key] = len(prefix_keys)
                prefix_keys.append(key)
            if user_id not in user_index:
                user_index[user_id] = len(user_ids)
                user_ids.append(user_id)

        if not prefix_keys or not user_ids:
            return None

        R = np.full((len(prefix_keys), len(user_ids)), np.nan, dtype=np.float32)
        for (key, user_id), (_, rating_value) in latest.items():
            R[key_index[key], user_index[user_id]] = float(rating_value)
        mask = ~np.isnan(R)
        return PBCFArtifacts(prefix_keys=prefix_keys, user_ids=user_ids, ratings=R, mask=mask)

    async def train(self, db: AsyncSession) -> None:
        """Fit latent factors on current matrix artifacts."""
        artifacts = await self.build_matrix(db)
        if artifacts is None:
            self.artifacts = None
            self.W = None
            self.H = None
            return
        R0 = artifacts.ratings
        mask = artifacts.mask
        n_prefix, n_users = R0.shape
        k = min(self.k, max(2, min(n_prefix, n_users)))
        W = self.rng.random((n_prefix, k), dtype=np.float32) + 0.1
        H = self.rng.random((k, n_users), dtype=np.float32) + 0.1
        eps = 1e-6
        for _ in range(self.iters):
            R = W @ H
            R[mask] = R0[mask]
            H *= (W.T @ R) / ((W.T @ W @ H) + eps)
            W *= (R @ H.T) / ((W @ (H @ H.T)) + eps)
        self.artifacts = artifacts
        self.W = W
        self.H = H

    async def predict_user_ratings(self, db: AsyncSession, user_id: str) -> dict[str, float]:
        """Predict per-prefix ratings for a known user ID."""
        if self.artifacts is None or self.W is None:
            await self.train(db)
        if self.artifacts is None or self.W is None:
            return {}
        artifacts = self.artifacts
        if user_id not in artifacts.user_ids:
            return {}
        user_idx = artifacts.user_ids.index(user_id)
        r0 = artifacts.ratings[:, user_idx].copy()
        mask = ~np.isnan(r0)
        h = self.rng.random((self.W.shape[1],), dtype=np.float32) + 0.1
        eps = 1e-6
        for _ in range(self.iters):
            r = self.W @ h
            r[mask] = r0[mask]
            h *= (self.W.T @ r) / ((self.W.T @ self.W @ h) + eps)
        r_pred = np.clip(self.W @ h, 1.0, 5.0)
        return {key: float(r_pred[i]) for i, key in enumerate(artifacts.prefix_keys)}

    def get_stats(self) -> dict[str, Any]:
        """Return lightweight diagnostics for model readiness/training size."""
        if self.artifacts is None or self.W is None:
            return {
                "trained": False,
                "prefix_count": 0,
                "user_count": 0,
                "ratings_count": 0,
                "missing_ratio": 1.0,
                "latent_dim": self.k,
            }
        ratings_count = int(self.artifacts.mask.sum())
        total = int(self.artifacts.ratings.size)
        missing_ratio = 1.0 - (ratings_count / total) if total else 1.0
        return {
            "trained": True,
            "prefix_count": len(self.artifacts.prefix_keys),
            "user_count": len(self.artifacts.user_ids),
            "ratings_count": ratings_count,
            "missing_ratio": round(missing_ratio, 3),
            "latent_dim": int(self.W.shape[1]),
        }
