from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from sqlalchemy import Float, and_, cast, select
from sqlalchemy.ext.asyncio import AsyncSession

from .db import ProductRecord, close_db, get_db, init_db, record_to_dict, verify_connection
from .models import Product, ProductOut, UserCreate, UserOut
from .category_profiles import normalize_category
from .services.recommender import recommender
from .services.schema_service import ensure_multicategory_compatibility
from .routes.game import router as game_router
from .routes.auth import router as auth_router
import logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

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
    if q:
        filters.append(ProductRecord.data["title"].as_string().ilike(f"%{q}%"))
    if vendor:
        filters.append(ProductRecord.data["vendor"].as_string().ilike(f"%{vendor}%"))
    if category:
        try:
            normalized = normalize_category(category)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        filters.append(ProductRecord.category == normalized)
    if price_min is not None:
        filters.append(cast(ProductRecord.data["price_min"].as_string(), Float) >= price_min)
    if price_max is not None:
        filters.append(cast(ProductRecord.data["price_max"].as_string(), Float) <= price_max)

    stmt = select(ProductRecord).offset(offset).limit(limit)
    if filters:
        stmt = stmt.where(and_(*filters))
    result = await db.execute(stmt)
    products = [record_to_dict(row) for row in result.scalars().all()]
    return [ProductOut.from_record(Product(**p)) for p in products]


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
