from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from bson import ObjectId

from .db import get_db, close_db, Settings, verify_connection
from .models import Product, ProductOut, UserCreate, UserOut
from .category_profiles import normalize_category
from .services.recommender import recommender
from .services.schema_service import ensure_multicategory_compatibility
from .routes.game import router as game_router
from .routes.auth import router as auth_router
from motor.motor_asyncio import AsyncIOMotorDatabase
import logging

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parents[2]
FRONTEND_DIR = BASE_DIR / "frontend"
FRONTEND_DIST_DIR = FRONTEND_DIR / "dist"

app = FastAPI(title="Decidio Prototype (MongoDB)")

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
    """Initialize the recommender on startup and verify MongoDB connection."""
    # Verify MongoDB connection
    is_connected = await verify_connection()
    if not is_connected:
        logger.warning("MongoDB connection verification failed, but proceeding with startup")
    
    from .db import get_client
    db = get_client()[Settings().mongodb_db_name]
    await ensure_multicategory_compatibility(db)
    await recommender.refresh(db)
    logger.info("Application startup completed")


@app.on_event("shutdown")
async def on_shutdown():
    """Close MongoDB connection on shutdown."""
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
    db: AsyncIOMotorDatabase = Depends(get_db),
):
    """List products with optional filtering."""
    query = {}

    if q:
        query["title"] = {"$regex": q, "$options": "i"}
    if vendor:
        query["vendor"] = {"$regex": vendor, "$options": "i"}
    if category:
        try:
            normalized = normalize_category(category)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        if normalized == "fountain_pens":
            query["$or"] = [{"category": "fountain_pens"}, {"category": {"$exists": False}}]
        else:
            query["category"] = normalized
    if price_min is not None:
        query["price_min"] = {"$gte": price_min}
    if price_max is not None:
        query["price_max"] = {"$lte": price_max}

    cursor = db.products.find(query).skip(offset).limit(limit)
    products = await cursor.to_list(length=limit)
    return [ProductOut.from_mongo(Product(**p)) for p in products]


@app.get("/api/products/{product_id}", response_model=ProductOut)
async def get_product(product_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get a specific product by ID."""
    if not ObjectId.is_valid(product_id):
        raise HTTPException(status_code=400, detail="Invalid product ID")

    product = await db.products.find_one({"_id": ObjectId(product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    return ProductOut.from_mongo(Product(**product))


# Include game routes
app.include_router(game_router)

# Include auth routes
app.include_router(auth_router)


# Mount frontend (production React build if available).
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
