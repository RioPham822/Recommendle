"""Pydantic domain and API DTO models used by the backend."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def new_id() -> str:
    """Generate compact hex identifier for model defaults."""
    return uuid4().hex


class BaseDocModel(BaseModel):
    """Base model for persisted documents."""

    id: Optional[str] = Field(default_factory=new_id, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class ProductImage(BaseDocModel):
    """Image metadata persisted alongside product data."""

    url: str
    alt: Optional[str] = None
    position: int = 0


class Product(BaseDocModel):
    """Generic product envelope with category and dynamic payload."""

    category: str = "fountain_pens"
    data: dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        extra="allow",
        json_encoders={datetime: lambda v: v.isoformat()},
    )

    @model_validator(mode="before")
    @classmethod
    def _coalesce_payload(cls, value: Any) -> Any:
        if not isinstance(value, dict):
            return value
        payload = dict(value.get("data") or {})
        core = {"_id", "id", "created_at", "category", "data"}
        for key, item in value.items():
            if key in core:
                continue
            payload.setdefault(key, item)
        normalized = dict(value)
        normalized["data"] = payload
        return normalized


class User(BaseDocModel):
    """User model used by API/domain layer."""

    username: str = Field(..., index=True, unique=True)
    role: str = "player"
    password_hash: str
    display_name: str
    games: list[str] = Field(default_factory=list)
    session_tokens: list[str] = Field(default_factory=list)


class PrefixRating(BaseDocModel):
    """Prefix rating event used to train/update preference models."""

    session_id: str = Field(..., description="Reference to session")
    rating: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Response models (DTOs)
class ProductOut(BaseModel):
    """Public product DTO returned by listing/detail endpoints."""

    id: str
    category: str = "fountain_pens"
    title: str
    vendor: Optional[str] = None
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def from_record(cls, product: Product) -> "ProductOut":
        """Build API DTO from internal product model."""
        data = dict(product.data or {})
        title = str(data.get("title") or "Untitled")
        vendor = data.get("vendor")
        if vendor is not None:
            vendor = str(vendor)
        return cls(
            id=str(product.id),
            category=product.category,
            title=title,
            vendor=vendor,
            data=data,
        )


class UserOut(BaseModel):
    """Public user DTO returned by auth endpoints."""

    id: str
    username: str
    role: str
    display_name: str
    created_at: datetime

    @classmethod
    def from_record(cls, user: User) -> "UserOut":
        """Build API DTO from internal user model."""
        return cls(
            id=str(user.id),
            username=user.username,
            role=user.role,
            display_name=user.display_name,
            created_at=user.created_at,
        )


class UserCreate(BaseModel):
    """Incoming payload for minimal user creation flows."""

    name: str


class RecommendationOut(BaseModel):
    """Recommendation response payload."""

    strong: list[ProductOut]
    wildcard: Optional[ProductOut]
    coherence_score: float
    predicted_prefix_rating: float
