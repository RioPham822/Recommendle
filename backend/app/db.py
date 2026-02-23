from __future__ import annotations

import os
from pathlib import Path
from typing import AsyncGenerator

from motor.motor_asyncio import AsyncIOMotorClient, AsyncIOMotorDatabase
from pydantic_settings import BaseSettings, SettingsConfigDict
import logging

logger = logging.getLogger(__name__)

ENV_PATH = Path(__file__).resolve().parents[1] / ".env"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(ENV_PATH),
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # MongoDB Settings
    mongodb_url: str = "mongodb://localhost:27017"
    mongodb_db_name: str = "decidio"
    mongodb_max_pool_size: int = 10
    mongodb_min_pool_size: int = 1
    tmdb_api_key: str = ""


settings = Settings()

# Global motor client
_client: AsyncIOMotorClient | None = None


def get_client() -> AsyncIOMotorClient:
    """Get or create the MongoDB client."""
    global _client
    if _client is None:
        _client = AsyncIOMotorClient(
            settings.mongodb_url,
            maxPoolSize=settings.mongodb_max_pool_size,
            minPoolSize=settings.mongodb_min_pool_size,
        )
    return _client


async def get_db() -> AsyncGenerator[AsyncIOMotorDatabase, None]:
    """Get database instance for dependency injection."""
    client = get_client()
    db = client[settings.mongodb_db_name]
    try:
        yield db
    finally:
        pass


async def close_db():
    """Close the MongoDB connection."""
    global _client
    if _client is not None:
        _client.close()
        _client = None
        logger.info("MongoDB connection closed")


async def verify_connection():
    """Verify MongoDB connection is working."""
    try:
        client = get_client()
        await client.admin.command('ping')
        logger.info("MongoDB connection verified successfully")
        return True
    except Exception as e:
        logger.error(f"Failed to verify MongoDB connection: {e}")
        return False
