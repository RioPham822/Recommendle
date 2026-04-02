"""Admin routes for user management, product management, and ML configuration."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy import Float, and_, cast, delete, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..category_profiles import get_category_profile, humanize_feature_list, normalize_category, supported_categories
from ..db import GameRecord, GameRoundRecord, PrefixRatingRecord, ProductRecord, UserRecord, get_db, record_to_dict
from ..services.auth import active_session_tokens, auth_service, require_admin
from ..services.ml_config import DEFAULT_ML_CONFIG, ml_config_service
from ..services.game_service import game_service
from ..services.recommender import recommender

router = APIRouter(prefix="/api/admin", tags=["admin"])


LIST_LIKE_FIELDS = {
    "tags",
    "genres",
    "keywords",
    "production_companies",
    "directors",
    "themes",
    "game_modes",
    "player_perspectives",
    "platforms",
    "nib_sizes",
}
EXCLUDED_PRODUCT_FIELDS = {
    "_id",
    "id",
    "images",
    "options",
    "source_id",
    "ingest_source",
    "schema_version",
}
PREFERRED_PRODUCT_FIELDS: dict[str, list[str]] = {
    "movies": [
        "title",
        "vendor",
        "release_year",
        "runtime_minutes",
        "vote_average",
        "vote_count",
        "status",
        "certification",
        "primary_country",
        "original_language",
        "genres",
        "production_companies",
        "directors",
        "keywords",
        "description",
        "url",
        "quality_score",
        "created_at",
    ],
    "games": [
        "title",
        "vendor",
        "release_year",
        "total_rating",
        "hypes",
        "game_status",
        "platforms",
        "genres",
        "themes",
        "game_modes",
        "player_perspectives",
        "keywords",
        "description",
        "url",
        "quality_score",
        "created_at",
    ],
    "fountain_pens": [
        "title",
        "vendor",
        "product_type",
        "price_min",
        "price_max",
        "currency",
        "nib_sizes",
        "tags",
        "description",
        "url",
        "quality_score",
        "created_at",
    ],
}


class AdminUserOut(BaseModel):
    id: str
    username: str
    display_name: str
    created_at: datetime
    updated_at: datetime
    active_sessions: int = 0


class MLConfigUpdateRequest(BaseModel):
    values: dict[str, float]


class ProductTableResponse(BaseModel):
    category: str
    total: int
    limit: int
    offset: int
    columns: list[dict[str, Any]]
    rows: list[dict[str, Any]]


class AdminUserMlStatsOut(BaseModel):
    user: dict[str, Any]
    profiles: list[dict[str, Any]]


def _preferred_product_columns(category: str) -> list[str]:
    return list(PREFERRED_PRODUCT_FIELDS.get(category, ["title", "vendor", "description", "url", "created_at"]))


def _column_kind(key: str) -> str:
    if key in {"thumbnail"}:
        return "thumbnail"
    if key in {"title"}:
        return "title"
    if key in {"description"}:
        return "long_text"
    if key in {"url"}:
        return "link"
    if key in LIST_LIKE_FIELDS:
        return "chips"
    if key in {"vote_average", "total_rating", "quality_score"}:
        return "rating"
    if key in {"vote_count", "hypes", "runtime_minutes", "release_year", "price_min", "price_max"}:
        return "number"
    if key in {"status", "game_status", "certification", "currency", "primary_country", "original_language"}:
        return "badge"
    if key in {"created_at"}:
        return "date"
    return "text"


def _split_list_value(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item).strip() for item in value if str(item).strip()]
    text = str(value).strip()
    if not text:
        return []
    if "|" in text:
        return [part.strip() for part in text.split("|") if part.strip()]
    if "," in text and len(text) < 160:
        return [part.strip() for part in text.split(",") if part.strip()]
    return [text]


async def _load_product_columns(db: AsyncSession, category: str) -> list[dict[str, str]]:
    rows = (
        await db.execute(
            select(ProductRecord.data)
            .where(ProductRecord.category == category)
            .limit(5000)
        )
    ).scalars().all()
    discovered_set: set[str] = set()
    for payload in rows:
        if not isinstance(payload, dict):
            continue
        discovered_set.update(str(key) for key in payload.keys())
    discovered = sorted(key for key in discovered_set if key not in EXCLUDED_PRODUCT_FIELDS)
    ordered = _preferred_product_columns(category)
    for key in discovered:
        if key not in ordered:
            ordered.append(key)
    columns = [
        {
            "key": key,
            "label": "Studio" if key == "vendor" and category in {"movies", "games"} else key.replace("_", " ").title(),
            "kind": _column_kind(key),
        }
        for key in ordered
        if key in discovered_set or key == "title"
    ]
    return [
        {
            "key": "thumbnail",
            "label": "Thumbnail",
            "kind": "thumbnail",
        },
        *columns,
    ]


def _coerce_cell_value(value: Any) -> Any:
    if isinstance(value, dict):
        return None
    return value


def _extract_image_url(value: Any) -> str | None:
    if isinstance(value, str):
        return value.strip() or None
    if isinstance(value, dict):
        candidate = value.get("url") or value.get("src")
        return str(candidate).strip() if candidate else None
    if isinstance(value, list):
        for item in value:
            candidate = _extract_image_url(item)
            if candidate:
                return candidate
    return None


def _product_row(record: ProductRecord, columns: list[dict[str, str]]) -> dict[str, Any]:
    payload = record_to_dict(record)
    image_url = _extract_image_url(payload.get("images"))
    row: dict[str, Any] = {
        "id": str(record.id),
        "category": record.category,
        "image_url": image_url,
        "thumbnail": image_url,
    }
    for column in columns:
        key = column["key"]
        value = _coerce_cell_value(payload.get(key))
        if column.get("kind") == "chips":
            row[key] = _split_list_value(value)
        else:
            row[key] = value
    return row


def _parse_filters(filters: str | None) -> dict[str, Any]:
    if not filters:
        return {}
    try:
        parsed = json.loads(filters)
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="Invalid filters JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status_code=400, detail="Filters must be a JSON object")
    return parsed


def _build_product_filters(category: str, search: str | None, filters: dict[str, Any]) -> list[Any]:
    conditions: list[Any] = [ProductRecord.category == category]
    if search:
        search_value = f"%{search.strip()}%"
        conditions.append(
            or_(
                ProductRecord.data["title"].as_string().ilike(search_value),
                ProductRecord.data["vendor"].as_string().ilike(search_value),
            )
        )
    for key, raw_value in filters.items():
        if raw_value in (None, "", []):
            continue
        if key in {"price_min", "price_max"}:
            try:
                numeric_value = float(raw_value)
            except (TypeError, ValueError) as exc:
                raise HTTPException(status_code=400, detail=f"Invalid numeric filter for '{key}'") from exc
            field_name = "price_min" if key == "price_min" else "price_max"
            operator = ">=" if key == "price_min" else "<="
            field = cast(ProductRecord.data[field_name].as_string(), Float)
            conditions.append(field >= numeric_value if operator == ">=" else field <= numeric_value)
            continue
        text_value = f"%{str(raw_value).strip()}%"
        conditions.append(ProductRecord.data[key].as_string().ilike(text_value))
    return conditions


def _summarize_model_state(category: str, state: dict[str, Any], all_selected_products: list[dict[str, Any]]) -> dict[str, Any]:
    model = game_service.recommender.model
    feature_space = game_service.recommender.feature_space
    if model is None or feature_space is None:
        return {
            "learned_preferences": [],
            "learned_dislikes": [],
            "hidden_preferences": [],
            "disliked_signals": [],
            "vector_strength": 0.0,
        }

    aligned_state = game_service._ensure_redesign_state(state)
    game_service._align_state_to_feature_space(model, aligned_state)
    raw_vec = aligned_state.get("user_vec") or []
    inv_index = {v: k for k, v in feature_space.feature_index.items()}
    weighted: list[tuple[str, float]] = []
    disliked: list[tuple[str, float]] = []
    for idx, raw in inv_index.items():
        if idx >= len(raw_vec):
            continue
        weight = float(raw_vec[idx] or 0.0)
        if weight >= 0.05:
            weighted.append((raw, round(weight, 3)))
        elif weight <= -0.05:
            disliked.append((raw, round(abs(weight), 3)))
    weighted.sort(key=lambda item: item[1], reverse=True)
    disliked.sort(key=lambda item: item[1], reverse=True)
    hidden_raw = model.detect_hidden_preferences(aligned_state, all_selected_products, top_n=8)
    disliked_tokens = list(state.get("disliked_tokens") or [])
    disliked_signals = humanize_feature_list([(token, 1.0) for token in disliked_tokens[:10]])
    return {
        "learned_preferences": humanize_feature_list(weighted[:10]),
        "learned_dislikes": humanize_feature_list(disliked[:8]),
        "hidden_preferences": humanize_feature_list([(item["feature"], round(item["latency"], 3)) for item in hidden_raw]),
        "disliked_signals": disliked_signals,
        "vector_strength": round(sum(abs(float(value or 0.0)) for value in raw_vec), 3),
        "selection_count": int(aligned_state.get("count") or 0),
        "negative_feedback_count": int(aligned_state.get("neg_count") or 0),
        "active_preference_ids": list(aligned_state.get("active_preference_ids") or []),
    }


@router.get("/me")
async def get_admin_me(admin: UserRecord = Depends(require_admin)):
    return {
        "id": admin.id,
        "username": admin.username,
        "role": admin.role,
        "display_name": admin.display_name,
    }


@router.get("/users", response_model=list[AdminUserOut])
async def list_users(
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    users = await auth_service.list_users(db)
    return [
        AdminUserOut(
            id=user["_id"],
            username=user["username"],
            display_name=user["display_name"],
            created_at=user["created_at"],
            updated_at=user["updated_at"],
            active_sessions=user["active_sessions"],
        )
        for user in users
    ]


@router.delete("/users/{user_id}")
async def delete_user_account(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    candidate_names = [name for name in {user.display_name, user.username} if name]
    games = (
        await db.execute(
            select(GameRecord.id).where(GameRecord.player_name.in_(candidate_names))
        )
    ).scalars().all()
    game_ids = [str(game_id) for game_id in games]

    if game_ids:
        await db.execute(delete(GameRoundRecord).where(GameRoundRecord.game_id.in_(game_ids)))
        await db.execute(delete(PrefixRatingRecord).where(PrefixRatingRecord.session_id.in_(game_ids)))
        await db.execute(delete(GameRecord).where(GameRecord.id.in_(game_ids)))

    await db.execute(delete(UserRecord).where(UserRecord.id == user_id))
    await db.commit()
    recommender.invalidate_ratings()
    return {
        "success": True,
        "deleted_game_count": len(game_ids),
    }


@router.post("/users/{user_id}/progress/clear")
async def clear_user_progress(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    candidate_names = [name for name in {user.display_name, user.username} if name]
    games = (
        await db.execute(
            select(GameRecord.id).where(GameRecord.player_name.in_(candidate_names))
        )
    ).scalars().all()
    game_ids = [str(game_id) for game_id in games]

    if game_ids:
        await db.execute(delete(GameRoundRecord).where(GameRoundRecord.game_id.in_(game_ids)))
        await db.execute(delete(PrefixRatingRecord).where(PrefixRatingRecord.session_id.in_(game_ids)))
        await db.execute(delete(GameRecord).where(GameRecord.id.in_(game_ids)))

    await db.commit()
    recommender.invalidate_ratings()
    return {
        "success": True,
        "cleared_game_count": len(game_ids),
    }


@router.get("/users/{user_id}/ml-stats", response_model=AdminUserMlStatsOut)
async def get_user_ml_stats(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    await game_service.recommender.ensure_fresh(db)
    profiles: list[dict[str, Any]] = []
    resumable_runs: list[dict[str, Any]] = []
    candidate_names = [name for name in {user.display_name, user.username} if name]
    for category in supported_categories():
        active_game_row = await db.scalar(
            select(GameRecord)
            .where(
                and_(
                    GameRecord.player_name.in_(candidate_names),
                    GameRecord.category == category,
                    GameRecord.status.in_(["onboarding", "ready", "playing"]),
                )
            )
            .order_by(GameRecord.updated_at.desc(), GameRecord.created_at.desc())
            .limit(1)
        )
        if active_game_row:
            active_game = record_to_dict(active_game_row)
            resumable_runs.append(
                {
                    "category": category,
                    "display_name": get_category_profile(category).display_name,
                    "game_id": active_game["_id"],
                    "status": active_game.get("status"),
                    "current_round": int(active_game.get("current_round") or 0),
                    "total_rounds": int(active_game.get("total_rounds") or 0),
                    "updated_at": active_game.get("updated_at"),
                    "player_name": active_game.get("player_name"),
                }
            )
        game_row = await db.scalar(
            select(GameRecord)
            .where(and_(GameRecord.player_name.in_(candidate_names), GameRecord.category == category))
            .order_by(GameRecord.updated_at.desc(), GameRecord.created_at.desc())
            .limit(1)
        )
        if not game_row:
            continue
        game = record_to_dict(game_row)
        state = game_service._ensure_redesign_state(game.get("model_state") or {})
        selected_ids = await game_service._current_selection_sequence(db, game)
        selected_products = await game_service._get_products_by_ids(
            db,
            selected_ids,
            projection=game_service._feature_projection(category),
        )
        summary = _summarize_model_state(category, state, selected_products)
        profiles.append(
            {
                "category": category,
                "display_name": get_category_profile(category).display_name,
                "status": game.get("status"),
                "rounds_played": game_service._rounds_played(game),
                "updated_at": game.get("updated_at"),
                "onboarding_selected_count": len(game.get("onboarding_selected_ids") or []),
                "preference_deck": await game_service._preference_deck(db, game),
                **summary,
            }
        )

    return AdminUserMlStatsOut(
        user={
            "id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "active_sessions": len(active_session_tokens(user.session_tokens)),
            "created_at": user.created_at,
            "updated_at": user.updated_at,
            "resumable_runs": resumable_runs,
        },
        profiles=profiles,
    )


@router.get("/ml-config")
async def get_ml_config_endpoint(
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    return await ml_config_service.ensure_loaded(db)


@router.patch("/ml-config")
async def update_ml_config(
    payload: MLConfigUpdateRequest,
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    try:
        updated = await ml_config_service.update(db, payload.values)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    return {
        "values": updated,
        "defaults": DEFAULT_ML_CONFIG,
    }


@router.get("/products", response_model=ProductTableResponse)
async def list_admin_products(
    category: str = Query(...),
    search: str | None = None,
    filters: str | None = None,
    limit: int = Query(default=100, ge=1, le=250),
    offset: int = Query(default=0, ge=0),
    sort_field: str = Query(default="title"),
    sort_dir: str = Query(default="asc"),
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    try:
        normalized_category = normalize_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filter_values = _parse_filters(filters)
    conditions = _build_product_filters(normalized_category, search, filter_values)

    count_stmt = select(func.count()).select_from(ProductRecord).where(and_(*conditions))
    total = int((await db.scalar(count_stmt)) or 0)

    if sort_field in {"created_at"}:
        sort_column = ProductRecord.created_at
    elif sort_field in {"id", "category"}:
        sort_column = getattr(ProductRecord, sort_field)
    else:
        sort_column = ProductRecord.data[sort_field].as_string()
    sort_expression = sort_column.desc() if sort_dir.lower() == "desc" else sort_column.asc()

    stmt = (
        select(ProductRecord)
        .where(and_(*conditions))
        .order_by(sort_expression, ProductRecord.id.asc())
        .offset(offset)
        .limit(limit)
    )
    rows = (await db.execute(stmt)).scalars().all()
    columns = await _load_product_columns(db, normalized_category)
    return ProductTableResponse(
        category=normalized_category,
        total=total,
        limit=limit,
        offset=offset,
        columns=columns,
        rows=[_product_row(record, columns) for record in rows],
    )


@router.get("/products/export")
async def export_products(
    category: str,
    search: str | None = None,
    filters: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: UserRecord = Depends(require_admin),
):
    try:
        normalized_category = normalize_category(category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    filter_values = _parse_filters(filters)
    conditions = _build_product_filters(normalized_category, search, filter_values)
    columns = await _load_product_columns(db, normalized_category)
    header = [column["key"] for column in columns]

    async def streamer():
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        yield buffer.getvalue()
        buffer.seek(0)
        buffer.truncate(0)

        batch_size = 1000
        offset = 0
        while True:
            stmt = (
                select(ProductRecord)
                .where(and_(*conditions))
                .order_by(ProductRecord.id.asc())
                .offset(offset)
                .limit(batch_size)
            )
            batch = (await db.execute(stmt)).scalars().all()
            if not batch:
                break
            for record in batch:
                row = _product_row(record, columns)
                writer.writerow(
                    [
                        " | ".join(value) if isinstance(value, list) else value
                        for key in header
                        for value in [row.get(key)]
                    ]
                )
            yield buffer.getvalue()
            buffer.seek(0)
            buffer.truncate(0)
            offset += batch_size

    filename = f"{normalized_category}-products-export.csv"
    headers = {"Content-Disposition": f'attachment; filename="{filename}"'}
    return StreamingResponse(streamer(), media_type="text/csv", headers=headers)


@router.get("/categories")
async def list_admin_categories(_: UserRecord = Depends(require_admin)):
    return [{"id": value, "display_name": get_category_profile(value).display_name} for value in supported_categories()]
