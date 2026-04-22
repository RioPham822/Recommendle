"""Database settings, ORM models, and async session lifecycle for Postgres."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, AsyncGenerator
from uuid import uuid4

from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy import JSON, Boolean, DateTime, Float, Integer, String, UniqueConstraint
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.sql import text

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    """Application settings loaded from `backend/.env`."""

    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    database_url: str = "postgresql+asyncpg://decidio:decidio_pass@localhost:5432/decidio"
    db_pool_size: int = 10
    db_max_overflow: int = 20
    tmdb_api_key: str = ""
    igdb_client_id: str = ""
    igdb_client_secret: str = ""
    admin_username: str = "admin"
    admin_password: str = "password"
    admin_display_name: str = "Administrator"


settings = Settings()


class Base(DeclarativeBase):
    """Base SQLAlchemy declarative model."""

    pass


def utcnow() -> datetime:
    """Return naive UTC datetime suitable for DB timestamp columns."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def new_id() -> str:
    """Generate compact hex identifier for application records."""
    return uuid4().hex


class ProductRecord(Base):
    """Stored product document (category + JSONB payload)."""

    __tablename__ = "products"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    category: Mapped[str] = mapped_column(String(100), default="fountain_pens", index=True)
    data: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class UserRecord(Base):
    """Stored user account and active session tokens."""

    __tablename__ = "users"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    username: Mapped[str] = mapped_column(String(80), nullable=False, unique=True, index=True)
    role: Mapped[str] = mapped_column(String(20), nullable=False, default="player", index=True)
    password_hash: Mapped[str] = mapped_column(String(300), nullable=False)
    display_name: Mapped[str] = mapped_column(String(100), nullable=False)
    games: Mapped[list[str]] = mapped_column(JSON, default=list)
    session_tokens: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class GameRecord(Base):
    """Stored game session state and score progression."""

    __tablename__ = "games"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    schema_version: Mapped[int] = mapped_column(Integer, default=2)
    player_name: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    category: Mapped[str] = mapped_column(String(100), default="fountain_pens", index=True)
    mode: Mapped[str] = mapped_column(String(20), default="classic", index=True)
    status: Mapped[str] = mapped_column(String(40), default="onboarding", index=True)
    current_round: Mapped[int] = mapped_column(Integer, default=0)
    total_rounds: Mapped[int] = mapped_column(Integer, default=5)
    human_score: Mapped[int] = mapped_column(Integer, default=0)
    ai_score: Mapped[int] = mapped_column(Integer, default=0)
    model_state: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    onboarding_pool_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    onboarding_selected_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    onboarding_rating: Mapped[int | None] = mapped_column(Integer)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class GameRoundRecord(Base):
    """Stored per-round data and AI/human outcomes for a game."""

    __tablename__ = "game_rounds"
    __table_args__ = (UniqueConstraint("game_id", "round_number", name="uq_game_round"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    schema_version: Mapped[int] = mapped_column(Integer, default=2)
    category: Mapped[str] = mapped_column(String(100), default="fountain_pens", index=True)
    game_id: Mapped[str] = mapped_column(String(32), index=True)
    round_number: Mapped[int] = mapped_column(Integer, index=True)
    candidate_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    pre_metrics: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    completed: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    human_pick_id: Mapped[str | None] = mapped_column(String(32))
    ai_pick_id: Mapped[str | None] = mapped_column(String(32))
    ai_confidence: Mapped[float | None] = mapped_column(Float)
    ai_top_k: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    ai_top3_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    ai_rank_of_pick: Mapped[int | None] = mapped_column(Integer)
    ai_correct: Mapped[bool | None] = mapped_column(Boolean)
    human_points: Mapped[int] = mapped_column(Integer, default=0)
    ai_points: Mapped[int] = mapped_column(Integer, default=0)
    post_metrics: Mapped[dict[str, Any] | None] = mapped_column(JSON)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PrefixRatingRecord(Base):
    """Stored onboarding prefix ratings used by PBCF training."""

    __tablename__ = "prefix_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    session_id: Mapped[str] = mapped_column(String(32), index=True)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)
    tags: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class AppConfigRecord(Base):
    """Key/value application configuration editable by admin users."""

    __tablename__ = "app_config"

    key: Mapped[str] = mapped_column(String(120), primary_key=True)
    value: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PersonaSimulationRunRecord(Base):
    """Stored admin persona simulation run state and event timeline."""

    __tablename__ = "persona_simulation_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    persona_id: Mapped[str] = mapped_column(String(120), nullable=False, index=True)
    persona_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(40), nullable=False, default="queued", index=True)
    game_id: Mapped[str | None] = mapped_column(String(32), index=True)
    config: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    persona_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    metrics: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    events: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    error_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


class PersonaProfileRecord(Base):
    """Canonical playable snapshot produced by the latest successful run of a persona."""

    __tablename__ = "persona_profiles"

    persona_id: Mapped[str] = mapped_column(String(120), primary_key=True)
    persona_name: Mapped[str] = mapped_column(String(160), nullable=False)
    category: Mapped[str] = mapped_column(String(100), nullable=False, index=True)
    source_run_id: Mapped[str | None] = mapped_column(String(32), index=True)
    source_game_id: Mapped[str | None] = mapped_column(String(32), index=True)
    persona_snapshot: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    model_state: Mapped[dict[str, Any]] = mapped_column(JSONB, default=dict)
    onboarding_selected_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    onboarding_rating: Mapped[int | None] = mapped_column(Integer)
    rounds_to_complete: Mapped[int] = mapped_column(Integer, default=0)
    match_rate: Mapped[float] = mapped_column(Float, default=0.0)
    longest_match_streak: Mapped[int] = mapped_column(Integer, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow, index=True)


def record_to_dict(record: Any) -> dict[str, Any]:
    """Normalize ORM row into existing dict shape expected by services."""
    if isinstance(record, ProductRecord):
        payload = dict(record.data or {})
        payload["_id"] = str(record.id)
        payload["category"] = record.category
        if "created_at" not in payload:
            payload["created_at"] = record.created_at
        return payload

    data: dict[str, Any] = {}
    for column in record.__table__.columns:
        key = column.name
        value = getattr(record, key)
        if key == "id":
            data["_id"] = str(value)
        else:
            data[key] = value
    return data


_engine: AsyncEngine | None = None
_session_factory: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    """Return singleton async SQLAlchemy engine."""
    global _engine
    if _engine is None:
        _engine = create_async_engine(
            settings.database_url,
            pool_size=settings.db_pool_size,
            max_overflow=settings.db_max_overflow,
        )
    return _engine


def get_session_factory() -> async_sessionmaker[AsyncSession]:
    """Return singleton async session factory."""
    global _session_factory
    if _session_factory is None:
        _session_factory = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _session_factory


async def init_db() -> None:
    """Create schema objects and ensure required indexes/columns exist."""
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
        await conn.execute(text("ALTER TABLE products ADD COLUMN IF NOT EXISTS data JSONB NOT NULL DEFAULT '{}'::jsonb"))
        await conn.execute(text("ALTER TABLE users ADD COLUMN IF NOT EXISTS role VARCHAR(20) NOT NULL DEFAULT 'player'"))
        await conn.execute(text("ALTER TABLE games ADD COLUMN IF NOT EXISTS mode VARCHAR(20) DEFAULT 'classic'"))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_games_category_status_created ON games(category, status, created_at DESC)")
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_games_category_player_created ON games(category, player_name, created_at DESC)"
            )
        )
        await conn.execute(text("ALTER TABLE games DROP CONSTRAINT IF EXISTS uq_game_player_category"))
        await conn.execute(text("DROP INDEX IF EXISTS uq_game_player_category"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_games_player_category ON games(player_name, category)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_users_role ON users(role)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_category ON products(category)"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_data_source_id ON products((data->>'source_id'))"))
        await conn.execute(
            text(
                "CREATE UNIQUE INDEX IF NOT EXISTS uq_products_category_source_id "
                "ON products(category, (data->>'source_id')) "
                "WHERE (data ? 'source_id') AND (COALESCE(data->>'source_id', '') <> '')"
            )
        )
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_data_title ON products((data->>'title'))"))
        await conn.execute(text("CREATE INDEX IF NOT EXISTS ix_products_data_vendor ON products((data->>'vendor'))"))
        await conn.execute(
            text("CREATE INDEX IF NOT EXISTS ix_rounds_game_created ON game_rounds(game_id, created_at DESC)")
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_persona_runs_status_created "
                "ON persona_simulation_runs(status, created_at DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_persona_runs_category_created "
                "ON persona_simulation_runs(category, created_at DESC)"
            )
        )
        await conn.execute(
            text(
                "CREATE INDEX IF NOT EXISTS ix_persona_profiles_category_updated "
                "ON persona_profiles(category, updated_at DESC)"
            )
        )


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield one async DB session per request/task."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        yield session


async def close_db() -> None:
    """Dispose engine/session factory and release DB resources."""
    global _engine, _session_factory
    if _engine is not None:
        await _engine.dispose()
        _engine = None
        _session_factory = None
        logger.info("Postgres connection closed")


async def verify_connection() -> bool:
    """Check DB connectivity with a lightweight query."""
    try:
        engine = get_engine()
        async with engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        logger.info("Postgres connection verified successfully")
        return True
    except Exception as exc:
        logger.error(f"Failed to verify Postgres connection: {exc}")
        return False
