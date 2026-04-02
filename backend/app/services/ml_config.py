"""Runtime ML configuration editable by admin users."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import AppConfigRecord

ML_CONFIG_KEY = "ml_parameters"
DEFAULT_ML_CONFIG: dict[str, float] = {
    "selection_weight": 1.0,
    "exception_weight": 0.35,
    "negative_weight": 0.6,
    "seed_weight": 0.45,
    "decay": 0.85,
    "bias_learning_rate": 0.25,
    "score_similarity_weight": 1.7,
    "score_norm_divisor": 3.0,
}
_ml_config_cache: dict[str, float] = dict(DEFAULT_ML_CONFIG)


def get_ml_config() -> dict[str, float]:
    """Return the in-memory ML tuning configuration."""
    return dict(_ml_config_cache)


class MLConfigService:
    """Persistence layer for tunable recommendation parameters."""

    @staticmethod
    async def ensure_loaded(db: AsyncSession) -> dict[str, float]:
        """Load config from DB or create defaults on first run."""
        record = await db.scalar(select(AppConfigRecord).where(AppConfigRecord.key == ML_CONFIG_KEY))
        if not record:
            record = AppConfigRecord(
                key=ML_CONFIG_KEY,
                value=dict(DEFAULT_ML_CONFIG),
                updated_at=datetime.utcnow(),
            )
            db.add(record)
            await db.commit()
        raw = record.value or {}
        merged = dict(DEFAULT_ML_CONFIG)
        for key, value in raw.items():
            try:
                merged[key] = float(value)
            except (TypeError, ValueError):
                continue
        _ml_config_cache.clear()
        _ml_config_cache.update(merged)
        return dict(_ml_config_cache)

    @staticmethod
    async def update(db: AsyncSession, values: dict[str, Any]) -> dict[str, float]:
        """Persist and refresh ML config values."""
        current = await MLConfigService.ensure_loaded(db)
        merged = dict(current)
        for key, default in DEFAULT_ML_CONFIG.items():
            if key not in values:
                continue
            try:
                merged[key] = float(values[key])
            except (TypeError, ValueError) as exc:
                raise ValueError(f"Invalid numeric value for '{key}'") from exc
        record = await db.scalar(select(AppConfigRecord).where(AppConfigRecord.key == ML_CONFIG_KEY))
        if not record:
            record = AppConfigRecord(key=ML_CONFIG_KEY, value=dict(merged), updated_at=datetime.utcnow())
            db.add(record)
        else:
            record.value = dict(merged)
            record.updated_at = datetime.utcnow()
        await db.commit()
        _ml_config_cache.clear()
        _ml_config_cache.update(merged)
        return dict(_ml_config_cache)


ml_config_service = MLConfigService()
