from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from bson import ObjectId

from .db_mongo import get_db, close_db, Settings, verify_connection
from .models_mongo import Product, ProductOut, UserCreate, UserOut, SessionCreate, SessionOut
from .models_mongo import SelectionCreate, PrefixRatingCreate, RecommendationOut
from .category_profiles import normalize_category
from .services.recommender_mongo import recommender_mongo
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
    
    from .db_mongo import get_client
    db = get_client()[Settings().mongodb_db_name]
    await ensure_multicategory_compatibility(db)
    await recommender_mongo.refresh(db)
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


@app.post("/api/users", response_model=UserOut)
async def create_user(payload: UserCreate, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Create a new user."""
    from datetime import datetime
    user_doc = {
        "name": payload.name,
        "sessions": [],
        "created_at": datetime.utcnow(),
    }
    result = await db.users.insert_one(user_doc)
    user = await db.users.find_one({"_id": result.inserted_id})
    return UserOut(id=str(user["_id"]), name=user["name"], created_at=user["created_at"])


@app.post("/api/sessions", response_model=SessionOut)
async def create_session(payload: SessionCreate, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Create a new session for a user."""
    if not ObjectId.is_valid(payload.user_id):
        raise HTTPException(status_code=400, detail="Invalid user ID")

    user = await db.users.find_one({"_id": ObjectId(payload.user_id)})
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session_doc = {
        "user_id": ObjectId(payload.user_id),
        "state": {},
        "selections": [],
        "prefix_ratings": [],
        "created_at": datetime.utcnow(),
    }
    result = await db.sessions.insert_one(session_doc)

    # Add session to user's sessions list
    await db.users.update_one(
        {"_id": ObjectId(payload.user_id)},
        {"$push": {"sessions": result.inserted_id}}
    )

    session = await db.sessions.find_one({"_id": result.inserted_id})
    return SessionOut(
        id=str(session["_id"]),
        user_id=str(session["user_id"]),
        created_at=session["created_at"]
    )


@app.post("/api/sessions/{session_id}/end")
async def end_session(session_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """End a session."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    result = await db.sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$set": {"state": None}}
    )

    if result.matched_count == 0:
        raise HTTPException(status_code=404, detail="Session not found")

    return {"status": "ended", "session_id": session_id}


@app.post("/api/sessions/{session_id}/select")
async def select_product(
    session_id: str,
    payload: SelectionCreate,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Select a product in a session."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")
    if not ObjectId.is_valid(payload.product_id):
        raise HTTPException(status_code=400, detail="Invalid product ID")

    session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    product = await db.products.find_one({"_id": ObjectId(payload.product_id)})
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    # Create selection
    selection_doc = {
        "session_id": ObjectId(session_id),
        "product_id": ObjectId(payload.product_id),
        "is_exception": payload.is_exception,
    }
    result = await db.selections.insert_one(selection_doc)

    # Update session
    await db.sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$push": {"selections": result.inserted_id}}
    )

    # Update recommender
    product_obj = Product(**product)
    await recommender_mongo.update_with_selection(
        db, session_id, session, product_obj, payload.is_exception
    )

    return {"status": "ok"}


@app.post("/api/sessions/{session_id}/rate")
async def rate_prefix(
    session_id: str,
    payload: PrefixRatingCreate,
    db: AsyncIOMotorDatabase = Depends(get_db)
):
    """Rate the current prefix (story-so-far)."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    # Create rating
    rating_doc = {
        "session_id": ObjectId(session_id),
        "rating": payload.rating,
        "tags": payload.tags,
    }
    result = await db.prefix_ratings.insert_one(rating_doc)

    # Update session
    await db.sessions.update_one(
        {"_id": ObjectId(session_id)},
        {"$push": {"prefix_ratings": result.inserted_id}}
    )

    # Update recommender
    await recommender_mongo.update_with_prefix_rating(
        db, session_id, session, payload.rating
    )

    return {"status": "ok"}


@app.get("/api/sessions/{session_id}/recommendations", response_model=RecommendationOut)
async def recommend(session_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get recommendations for a session."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    result = await recommender_mongo.recommend(db, session_id, session)

    return RecommendationOut(
        strong=[ProductOut.from_mongo(p) for p in result["strong"]],
        wildcard=ProductOut.from_mongo(result["wildcard"]) if result["wildcard"] else None,
        coherence_score=result["coherence_score"],
        predicted_prefix_rating=result["predicted_prefix_rating"],
    )


@app.get("/api/sessions/{session_id}/selections", response_model=list[ProductOut])
async def list_selections(session_id: str, db: AsyncIOMotorDatabase = Depends(get_db)):
    """List all selections in a session."""
    if not ObjectId.is_valid(session_id):
        raise HTTPException(status_code=400, detail="Invalid session ID")

    session = await db.sessions.find_one({"_id": ObjectId(session_id)})
    if not session:
        raise HTTPException(status_code=404, detail="Session not found")

    selection_ids = session.get("selections", [])
    if not selection_ids:
        return []

    # Get all selections and then their products
    selections_cursor = db.selections.find({"_id": {"$in": [ObjectId(sid) for sid in selection_ids]}})
    selections = await selections_cursor.to_list(length=None)

    product_ids = [ObjectId(s["product_id"]) for s in selections]
    products_cursor = db.products.find({"_id": {"$in": product_ids}})
    products = await products_cursor.to_list(length=None)

    product_map = {str(p["_id"]): ProductOut.from_mongo(Product(**p)) for p in products}

    # Return products in selection order
    ordered = []
    for sel in selections:
        product_id = str(sel["product_id"])
        if product_id in product_map:
            ordered.append(product_map[product_id])

    return ordered


@app.get("/api/debug/pbcf")
async def pbcf_debug(db: AsyncIOMotorDatabase = Depends(get_db)):
    """Get PBCF model statistics for debugging."""
    return await recommender_mongo.get_pbcf_stats(db)


# Include game routes
app.include_router(game_router)

# Include auth routes
app.include_router(auth_router)


# Mount frontend (production React build if available).
if FRONTEND_DIST_DIR.exists():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST_DIR, html=True), name="frontend")
else:
    app.mount("/", StaticFiles(directory=FRONTEND_DIR, html=True), name="frontend")
