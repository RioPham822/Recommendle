"""Pydantic request/response schemas for game APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class ProductCard(BaseModel):
    """Compact product representation used in gameplay responses."""

    id: str
    category: str = "fountain_pens"
    title: str
    vendor: str | None = None
    subtitle: str | None = None
    price_min: float | None = None
    price_max: float | None = None
    attributes: dict[str, Any] = Field(default_factory=dict)
    meta_badges: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = None


class MetricsOut(BaseModel):
    """Coherence and prefix-rating diagnostics returned by API."""

    coherence_score: float
    predicted_prefix_rating: float


class GameCreate(BaseModel):
    """Payload for creating a new game session."""

    player_name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(default="fountain_pens")


class GameOut(BaseModel):
    """API response after game creation."""

    id: str
    player_name: str
    category: str = "fountain_pens"
    status: str
    total_rounds: int
    human_score: int
    ai_score: int
    created_at: datetime


class OnboardingOut(BaseModel):
    """Onboarding pool response."""

    game_id: str
    category: str = "fountain_pens"
    pool_size: int
    category_copy: dict[str, str] = Field(default_factory=dict)
    products: list[ProductCard]


class OnboardingSubmit(BaseModel):
    """Onboarding submission payload."""

    selected_product_ids: list[str]
    rating: int = Field(..., ge=1, le=5)


class OnboardingSubmitOut(BaseModel):
    """Result after onboarding picks are accepted."""

    accepted: bool
    coherence_score: float
    predicted_prefix_rating: float
    next_round: int


class RoundStartOut(BaseModel):
    """Response payload for starting a round."""

    round_number: int
    category: str = "fountain_pens"
    category_copy: dict[str, str] = Field(default_factory=dict)
    candidates: list[ProductCard]
    pre_round_metrics: MetricsOut


class RoundPickSubmit(BaseModel):
    """Payload for submitting one pick in a round."""

    product_id: str


class ScoredProductCard(ProductCard):
    """Product card augmented with model score."""

    score: float


class AIExplanation(BaseModel):
    """Structured explanation block for round outcomes."""

    reason: str
    top_candidates: list[ScoredProductCard]
    learned_preferences: list[list] = Field(default_factory=list)
    learned_dislikes: list[list] = Field(default_factory=list)
    shared_features: list[str] = Field(default_factory=list)
    hidden_preferences: list[list] = Field(default_factory=list)
    hidden_preference_hints: list[str] = Field(default_factory=list)


class RoundResultOut(BaseModel):
    """Full response for a completed round."""

    round_number: int
    category: str = "fountain_pens"
    category_copy: dict[str, str] = Field(default_factory=dict)
    human_pick: ProductCard
    ai_pick: ScoredProductCard
    ai_correct: bool
    ai_exact: bool = False
    ai_rank_of_pick: int = 1
    ai_top3_ids: list[str] = Field(default_factory=list)
    human_points: int
    ai_points: int
    total_human_score: int
    total_ai_score: int
    ai_explanation: AIExplanation
    post_round_metrics: MetricsOut
    game_complete: bool


class RoundStatOut(BaseModel):
    """Per-round stats used in summary responses."""

    round_number: int
    ai_correct: bool
    ai_rank_of_pick: int | None = None
    ai_confidence: float = 0
    coherence: float = 0
    predicted_rating: float = 3.0
    cumulative_ai: int = 0
    cumulative_human: int = 0


class AccuracySummary(BaseModel):
    """Aggregate accuracy metrics for a completed game."""

    top3_correct: int
    exact_correct: int
    top3_rate: float
    exact_rate: float


class GameSummaryOut(BaseModel):
    """Final summary payload for a completed game."""

    game_id: str
    player_name: str
    category: str = "fountain_pens"
    category_copy: dict[str, str] = Field(default_factory=dict)
    total_rounds: int
    human_score: int
    ai_score: int
    accuracy: AccuracySummary
    round_stats: list[RoundStatOut]
    learned_preferences: list[list] = Field(default_factory=list)
    learned_dislikes: list[list] = Field(default_factory=list)
    top5_recommendations: list[ScoredProductCard]
    hidden_preferences: list[list] = Field(default_factory=list)
    hidden_gems_products: list[ScoredProductCard] = Field(default_factory=list)
    hidden_gems_explanation: str = ""


class GameStatusOut(BaseModel):
    """Current game status payload."""

    id: str
    player_name: str
    category: str = "fountain_pens"
    category_copy: dict[str, str] = Field(default_factory=dict)
    status: str
    current_round: int
    total_rounds: int
    human_score: int
    ai_score: int
    onboarding_complete: bool
    onboarding_selected_count: int
    round_in_progress: int | None = None


class LeaderboardEntry(BaseModel):
    """Single leaderboard row."""

    rank: int
    player_name: str
    category: str = "fountain_pens"
    human_score: int
    ai_score: int
    score_difference: int
    rounds_completed: int
    created_at: datetime


class PlayerGameEntry(BaseModel):
    """Single historical game row for a player."""

    game_id: str
    player_name: str
    category: str = "fountain_pens"
    human_score: int
    ai_score: int
    score_difference: int
    rounds_played: int
    ai_accuracy: float
    created_at: datetime


class CategoryOut(BaseModel):
    """Available category metadata and inventory count."""

    id: str
    display_name: str
    item_singular: str
    item_plural: str
    available_count: int
