"""Schemas for admin persona simulation APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field

from .schemas_game import GameStatusOut, GameSummaryOut


class PersonaDefinitionOut(BaseModel):
    """Bundled persona definition exposed in the admin UI."""

    id: str
    category: str
    display_name: str
    summary: str
    hard_likes: dict[str, list[str]] = Field(default_factory=dict)
    soft_likes: dict[str, list[str]] = Field(default_factory=dict)
    dislikes: dict[str, list[str]] = Field(default_factory=dict)
    numeric_preferences: dict[str, dict[str, float]] = Field(default_factory=dict)
    behavior: dict[str, Any] = Field(default_factory=dict)


class PersonaSimulationLaunchRequest(BaseModel):
    """Request payload to start one persona simulation run."""

    persona_id: str
    match_streak_target: int = Field(default=5, ge=1, le=50)
    max_rounds: int = Field(default=40, ge=1, le=200)


class PersonaSimulationEventOut(BaseModel):
    """Structured event shown in the admin detail panel."""

    type: str
    timestamp: datetime
    title: str
    detail: str = ""
    round_number: int | None = None
    data: dict[str, Any] = Field(default_factory=dict)


class PersonaSimulationRunOut(BaseModel):
    """List view payload for persona simulation runs."""

    id: str
    persona_id: str
    persona_name: str
    category: str
    status: str
    game_id: str | None = None
    created_at: datetime
    updated_at: datetime
    started_at: datetime | None = None
    completed_at: datetime | None = None
    current_round: int = 0
    rounds_played: int = 0
    current_match_streak: int = 0
    longest_match_streak: int = 0
    match_streak_target: int = 5
    total_matches: int = 0
    latest_message: str = ""
    error_message: str | None = None
    has_active_profile: bool = False
    metrics: dict[str, Any] = Field(default_factory=dict)


class PersonaSimulationRunDetailOut(PersonaSimulationRunOut):
    """Detail payload for one persona simulation run."""

    config: dict[str, Any] = Field(default_factory=dict)
    persona: PersonaDefinitionOut
    events: list[PersonaSimulationEventOut] = Field(default_factory=list)
    game_status: GameStatusOut | None = None
    final_summary: GameSummaryOut | None = None
