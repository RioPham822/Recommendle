from __future__ import annotations

from datetime import datetime
from typing import Any, Optional
from uuid import uuid4

from pydantic import BaseModel, Field


def new_id() -> str:
    return uuid4().hex


class BaseDocModel(BaseModel):
    """Base model for persisted game documents."""

    id: Optional[str] = Field(default_factory=new_id, alias="_id")
    created_at: datetime = Field(default_factory=datetime.utcnow)

    model_config = {
        "populate_by_name": True,
        "arbitrary_types_allowed": True,
    }


class GameSession(BaseDocModel):
    """A complete game session with multiple rounds."""
    player_name: str
    status: str = "waiting"  # waiting, playing, completed
    current_round: int = 0
    total_rounds: int = 5
    human_score: int = 0
    ai_score: int = 0
    rounds: list[str] = Field(default_factory=list)


class GameRound(BaseDocModel):
    """A single round in the game."""
    game_session_id: str
    round_number: int
    mystery_user_id: str  # The user from the dataset we're predicting
    clue_pen_ids: list[str]  # 4 pens shown to players
    target_pen_id: str  # The 5th pen (actual answer)
    human_prediction_id: Optional[str] = None
    ai_prediction_id: Optional[str] = None
    human_correct: Optional[bool] = None
    ai_correct: Optional[bool] = None
    ai_confidence: Optional[float] = None  # AI's confidence in its prediction
    completed: bool = False


class UserSelection(BaseDocModel):
    """Track a user's selections for training the model."""
    user_id: str  # Can be "dataset_user_{original_id}" for migrated users
    product_id: str
    rating: Optional[int] = None  # 1-5 if explicitly rated
    is_exception: bool = False
    created_at: datetime = Field(default_factory=datetime.utcnow)
