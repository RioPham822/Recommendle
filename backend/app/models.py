from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict
from bson import ObjectId


class PyObjectId(ObjectId):
    """Pydantic validator for MongoDB ObjectId."""

    @classmethod
    def __get_pydantic_core_schema__(cls, source_type, handler):
        from pydantic_core import core_schema
        return core_schema.with_info_plain_validator_function(
            cls.validate,
            serialization=core_schema.plain_serializer_function_ser_schema(str),
        )

    @classmethod
    def validate(cls, v, _info):
        if not isinstance(v, ObjectId):
            if isinstance(v, str) and ObjectId.is_valid(v):
                return ObjectId(v)
            raise ValueError("Invalid ObjectId")
        return v


class MongoModel(BaseModel):
    """Base model for MongoDB documents."""

    id: Optional[PyObjectId] = Field(default_factory=PyObjectId, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
    )


class ProductImage(MongoModel):
    url: str
    alt: Optional[str] = None
    position: int = 0


class Product(MongoModel):
    source_id: str = Field(..., index=True)
    title: str
    category: str = "fountain_pens"
    handle: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: str = "USD"
    tags: list[str] = Field(default_factory=list)
    options: dict[str, list[str]] = Field(default_factory=dict)
    # Movie-specific normalized fields (still stored in products collection).
    release_year: Optional[int] = None
    runtime_minutes: Optional[int] = None
    vote_average: Optional[float] = None
    popularity: Optional[float] = None
    original_language: Optional[str] = None
    certification: Optional[str] = None
    primary_country: Optional[str] = None
    decade_bucket: Optional[str] = None
    runtime_bucket: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    production_companies: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    url: Optional[str] = None
    images: list[ProductImage] = Field(default_factory=list)

    model_config = ConfigDict(
        populate_by_name=True,
        arbitrary_types_allowed=True,
        json_encoders={datetime: lambda v: v.isoformat()},
    )


class User(MongoModel):
    username: str = Field(..., index=True, unique=True)
    password_hash: str
    display_name: str
    games: list[PyObjectId] = Field(default_factory=list)
    session_tokens: list[str] = Field(default_factory=list)


class PrefixRating(MongoModel):
    session_id: PyObjectId = Field(..., description="Reference to session")
    rating: int = Field(..., ge=1, le=5)
    tags: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=datetime.utcnow)


# Response models (DTOs)
class ProductOut(BaseModel):
    id: str
    source_id: str
    title: str
    category: str = "fountain_pens"
    handle: Optional[str] = None
    vendor: Optional[str] = None
    product_type: Optional[str] = None
    price_min: Optional[float] = None
    price_max: Optional[float] = None
    currency: str
    tags: list[str]
    options: dict[str, list[str]]
    release_year: Optional[int] = None
    runtime_minutes: Optional[int] = None
    vote_average: Optional[float] = None
    popularity: Optional[float] = None
    original_language: Optional[str] = None
    certification: Optional[str] = None
    primary_country: Optional[str] = None
    decade_bucket: Optional[str] = None
    runtime_bucket: Optional[str] = None
    genres: list[str] = Field(default_factory=list)
    keywords: list[str] = Field(default_factory=list)
    production_companies: list[str] = Field(default_factory=list)
    directors: list[str] = Field(default_factory=list)
    description: Optional[str] = None
    url: Optional[str] = None
    images: list[ProductImage]

    @classmethod
    def from_mongo(cls, product: Product) -> "ProductOut":
        return cls(
            id=str(product.id),
            source_id=product.source_id,
            title=product.title,
            category=product.category,
            handle=product.handle,
            vendor=product.vendor,
            product_type=product.product_type,
            price_min=product.price_min,
            price_max=product.price_max,
            currency=product.currency,
            tags=product.tags,
            options=product.options,
            release_year=product.release_year,
            runtime_minutes=product.runtime_minutes,
            vote_average=product.vote_average,
            popularity=product.popularity,
            original_language=product.original_language,
            certification=product.certification,
            primary_country=product.primary_country,
            decade_bucket=product.decade_bucket,
            runtime_bucket=product.runtime_bucket,
            genres=product.genres,
            keywords=product.keywords,
            production_companies=product.production_companies,
            directors=product.directors,
            description=product.description,
            url=product.url,
            images=product.images,
        )


class UserOut(BaseModel):
    id: str
    username: str
    display_name: str
    created_at: datetime

    @classmethod
    def from_mongo(cls, user: User) -> "UserOut":
        return cls(id=str(user.id), username=user.username, display_name=user.display_name, created_at=user.created_at)


class UserCreate(BaseModel):
    name: str


class RecommendationOut(BaseModel):
    strong: list[ProductOut]
    wildcard: Optional[ProductOut]
    coherence_score: float
    predicted_prefix_rating: float
