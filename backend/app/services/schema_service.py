from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import ProductRecord

MIGRATION_COMMAND = "python -m scripts.load_db"


async def ensure_multicategory_compatibility(db: AsyncSession) -> None:
    """Validate startup schema expectations for category-aware gameplay."""
    missing_categories = await db.scalar(
        select(func.count()).select_from(ProductRecord).where(ProductRecord.category.is_(None))
    )
    if missing_categories > 0:
        raise RuntimeError(
            "Detected products without `category` field. "
            f"Run `{MIGRATION_COMMAND}` before starting the API "
            f"(missing documents: {missing_categories})."
        )
