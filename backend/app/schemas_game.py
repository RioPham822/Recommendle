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
    attributes: dict[str, Any] = Field(default_factory=dict)
    meta_badges: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    image_url: str | None = None
    description: str | None = None
    url: str | None = None
    predicted_match_features: list[str] = Field(default_factory=list)


class MetricsOut(BaseModel):
    """Coherence and prefix-rating diagnostics returned by API."""

    coherence_score: float
    predicted_prefix_rating: float


class GameCreate(BaseModel):
    """Payload for creating a new game session."""

    player_name: str = Field(..., min_length=1, max_length=80)
    category: str = Field(default="fountain_pens")
    mode: str = Field(default="classic")
    fresh_start: bool = Field(default=False)


class GameOut(BaseModel):
    """API response after game creation."""

    id: str
    schema_version: int = 2
    player_name: str
    category: str = "fountain_pens"
    mode: str = "classic"
    status: str
    total_rounds: int
    human_score: int
    ai_score: int
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    rounds_played: int = 0
    created_at: datetime
    resumed: bool = False


class ResumableGameOut(BaseModel):
    """Whether player/category has an active game to continue."""

    exists: bool
    can_start_fresh: bool = False
    game_id: str | None = None
    player_name: str | None = None
    category: str = "fountain_pens"
    status: str | None = None
    current_round: int | None = None
    total_rounds: int | None = None


class OnboardingOut(BaseModel):
    """Onboarding pool response."""

    game_id: str
    category: str = "fountain_pens"
    pool_size: int
    category_copy: dict[str, str] = Field(default_factory=dict)
    display_schema: dict[str, Any] = Field(default_factory=dict)
    preference_deck: list[ProductCard] = Field(default_factory=list)
    products: list[ProductCard]


class OnboardingSubmit(BaseModel):
    """Onboarding submission payload."""

    selected_product_ids: list[str]
    rating: int = Field(..., ge=1, le=5)


class OnboardingRefreshSubmit(BaseModel):
    """Payload for refreshing onboarding while preserving current selections."""

    selected_product_ids: list[str] = Field(default_factory=list)


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
    round_mode: str = "classic"
    category_copy: dict[str, str] = Field(default_factory=dict)
    display_schema: dict[str, Any] = Field(default_factory=dict)
    preference_deck: list[ProductCard] = Field(default_factory=list)
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    rounds_played: int = 0
    round_intro_title: str = ""
    round_intro_body: str = ""
    candidates: list[ProductCard]
    pre_round_metrics: MetricsOut


class RoundPickSubmit(BaseModel):
    """Payload for submitting one pick in a round."""

    product_id: str
    less_like_ids: list[str] = Field(default_factory=list)


class RoundRefreshSubmit(BaseModel):
    """Payload for refreshing a round with optional less-like selections."""

    less_like_ids: list[str] = Field(default_factory=list)


class FeedbackSubmit(BaseModel):
    """Payload for in-game feedback (beta mode)."""

    product_id: str
    action: str


class FeedbackOut(BaseModel):
    """Result after feedback is accepted."""

    accepted: bool
    action: str
    product_id: str


class SeedPreferencesSubmit(BaseModel):
    """Payload for seeding beta preferences before onboarding."""

    likes: dict[str, list[str]] = Field(default_factory=dict)
    dislikes: dict[str, list[str]] = Field(default_factory=dict)
    like_product_ids: list[str] = Field(default_factory=list)
    dislike_product_ids: list[str] = Field(default_factory=list)


class SeedPreferencesOut(BaseModel):
    """Result after seed preferences are accepted."""

    accepted: bool


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
    current_match_features: list[str] = Field(default_factory=list)


class RoundResultOut(BaseModel):
    """Full response for a completed round."""

    round_number: int
    category: str = "fountain_pens"
    round_mode: str = "classic"
    category_copy: dict[str, str] = Field(default_factory=dict)
    preference_deck: list[ProductCard] = Field(default_factory=list)
    human_pick: ProductCard
    ai_pick: ScoredProductCard
    ai_correct: bool
    ai_exact: bool = False
    ai_rank_of_pick: int = 1
    ai_top3_ids: list[str] = Field(default_factory=list)
    ai_top5_ids: list[str] = Field(default_factory=list)
    preference_match: bool = False
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    rounds_played: int = 0
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
    preference_match: bool = False
    current_match_streak: int = 0


class AccuracySummary(BaseModel):
    """Aggregate accuracy metrics for a completed game."""

    top3_correct: int
    exact_correct: int
    top3_rate: float
    exact_rate: float


class GameSummaryOut(BaseModel):
    """Final summary payload for a completed game."""

    game_id: str
    schema_version: int = 2
    player_name: str
    category: str = "fountain_pens"
    mode: str = "classic"
    category_copy: dict[str, str] = Field(default_factory=dict)
    total_rounds: int
    human_score: int
    ai_score: int
    rounds_played: int = 0
    total_matches: int = 0
    match_rate: float = 0.0
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
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
    schema_version: int = 2
    player_name: str
    category: str = "fountain_pens"
    mode: str = "classic"
    category_copy: dict[str, str] = Field(default_factory=dict)
    status: str
    current_round: int
    total_rounds: int
    human_score: int
    ai_score: int
    preference_deck: list[ProductCard] = Field(default_factory=list)
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    rounds_played: int = 0
    onboarding_complete: bool
    onboarding_selected_count: int
    round_in_progress: int | None = None


class LeaderboardEntry(BaseModel):
    """Single leaderboard row."""

    rank: int
    schema_version: int = 2
    player_name: str
    category: str = "fountain_pens"
    human_score: int
    ai_score: int
    score_difference: int
    rounds_completed: int
    rounds_to_complete: int = 0
    longest_match_streak: int = 0
    match_rate: float = 0.0
    created_at: datetime


class PlayerGameEntry(BaseModel):
    """Single historical game row for a player."""

    game_id: str
    schema_version: int = 2
    player_name: str
    category: str = "fountain_pens"
    human_score: int
    ai_score: int
    score_difference: int
    rounds_played: int
    ai_accuracy: float
    rounds_to_complete: int = 0
    longest_match_streak: int = 0
    match_rate: float = 0.0
    created_at: datetime


class CategoryOut(BaseModel):
    """Available category metadata and inventory count."""

    id: str
    display_name: str
    item_singular: str
    item_plural: str
    available_count: int


class PreferenceUpdateSubmit(BaseModel):
    """Payload for editing the active preference deck."""

    active_preference_ids: list[str]


class PreferenceUpdateOut(BaseModel):
    """Result after rebuilding a game's active preference deck."""

    game_id: str
    schema_version: int = 3
    category: str = "fountain_pens"
    category_copy: dict[str, str] = Field(default_factory=dict)
    display_schema: dict[str, Any] = Field(default_factory=dict)
    preference_deck: list[ProductCard] = Field(default_factory=list)
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    rounds_played: int = 0
    round: RoundStartOut | None = None
