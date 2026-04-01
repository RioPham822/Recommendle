"""FastAPI application entrypoint for Decidio backend."""

from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from difflib import SequenceMatcher
from sqlalchemy import Float, and_, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .category_profiles import normalize_category
from .db import (
    ProductRecord,
    close_db,
    get_db,
    init_db,
    record_to_dict,
    verify_connection,
)
from .models import Product, ProductOut, UserCreate, UserOut
from .routes.auth import router as auth_router
from .routes.game import router as game_router
from .services.recommender import recommender
from .services.schema_service import ensure_multicategory_compatibility

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"
MIN_MOVIE_VOTE_COUNT = 1000

app = FastAPI(title="Decidio Prototype (Postgres)")

# CORS configuration: allow Render production and local development
allowed_origins = [
    "https://recommendle-frontend.onrender.com",  # Production
    "http://localhost:5173",  # Local frontend (Vite dev server)
    "http://127.0.0.1:5173",  # Local frontend alternative
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
async def on_startup():
    """Initialize the recommender on startup and verify Postgres connection."""
    await init_db()
    is_connected = await verify_connection()
    if not is_connected:
        logger.warning("Postgres connection verification failed, but proceeding with startup")

    db_gen = get_db()
    db = await anext(db_gen)
    await ensure_multicategory_compatibility(db)
    await recommender.refresh(db)
    await db_gen.aclose()
    logger.info("Application startup completed")


@app.on_event("shutdown")
async def on_shutdown():
    """Close Postgres connection on shutdown."""
    await close_db()


@app.get("/api/products", response_model=list[ProductOut])
async def list_products(
    q: Optional[str] = None,
    vendor: Optional[str] = None,
    category: Optional[str] = None,
    price_min: Optional[float] = None,
    price_max: Optional[float] = None,
    limit: int = 50,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """List products with optional filtering."""
    filters = []
    normalized_category: str | None = None
    if q:
        filters.append(ProductRecord.data["title"].as_string().ilike(f"%{q}%"))
    if vendor:
        filters.append(ProductRecord.data["vendor"].as_string().ilike(f"%{vendor}%"))
    if category:
        try:
            normalized_category = normalize_category(category)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filters.append(ProductRecord.category == normalized_category)
    if price_min is not None:
        filters.append(cast(ProductRecord.data["price_min"].as_string(), Float) >= price_min)
    if price_max is not None:
        filters.append(cast(ProductRecord.data["price_max"].as_string(), Float) <= price_max)

    stmt = select(ProductRecord).offset(offset).limit(limit)
    if filters:
        stmt = stmt.where(and_(*filters))
    result = await db.execute(stmt)
    products = [record_to_dict(row) for row in result.scalars().all()]
    products = _filter_visible_products(products, normalized_category or "")
    return [ProductOut.from_record(Product(**p)) for p in products]


def _normalize_text(text: str) -> str:
    cleaned = re.sub(r"[^a-z0-9]+", " ", text.lower())
    return cleaned.strip()


def _filter_visible_products(products: list[dict], category: str) -> list[dict]:
    if category != "movies":
        return products
    visible: list[dict] = []
    for product in products:
        try:
            vote_count = int(product.get("vote_count") or 0)
        except (TypeError, ValueError):
            vote_count = 0
        if vote_count >= MIN_MOVIE_VOTE_COUNT:
            visible.append(product)
    return visible


@app.get("/api/products/search", response_model=list[ProductOut])
async def search_products(
    q: str,
    category: str = "movies",
    limit: int = 12,
    fuzzy: bool = True,
    db: AsyncSession = Depends(get_db),
):
    """Search products by title with optional fuzzy matching."""
    query = _normalize_text(q or "")
    if len(query) < 2:
        return []
    try:
        normalized = normalize_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    tokens = query.split()
    filters = [ProductRecord.category == normalized]
    if tokens:
        token_filters = [ProductRecord.data["title"].as_string().ilike(f"%{token}%") for token in tokens]
        filters.append(or_(*token_filters))
    stmt = select(ProductRecord).where(and_(*filters))
    pool_limit = max(40, min(200, int(limit) * 8))
    stmt = stmt.limit(pool_limit)
    rows = (await db.execute(stmt)).scalars().all()
    products = _filter_visible_products([record_to_dict(row) for row in rows], normalized)

    if not fuzzy:
        return [ProductOut.from_record(Product(**p)) for p in products[:limit]]

    def score_for(product: dict) -> float:
        title = _normalize_text(str(product.get("title") or ""))
        ratio = SequenceMatcher(None, query, title).ratio()
        if tokens and all(token in title for token in tokens):
            ratio += 0.15
        return ratio

    scored = sorted(products, key=score_for, reverse=True)
    return [ProductOut.from_record(Product(**p)) for p in scored[:limit]]


@app.get("/api/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, db: AsyncSession = Depends(get_db)):
    """Get a specific product by ID."""
    result = await db.execute(select(ProductRecord).where(ProductRecord.id == product_id))
    row = result.scalar_one_or_none()
    product = record_to_dict(row) if row else None
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductOut.from_record(Product(**product))


# Include game routes
app.include_router(game_router)

# Include auth routes
app.include_router(auth_router)


# Mount frontend (production React build if available).
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
elif FRONTEND_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
