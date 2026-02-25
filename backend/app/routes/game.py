"""HTTP routes for game lifecycle, rounds, leaderboard, and summaries."""

from __future__ import annotations

from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..schemas_game import (
    CategoryOut,
    GameCreate,
    GameOut,
    GameStatusOut,
    GameSummaryOut,
    LeaderboardEntry,
    OnboardingOut,
    OnboardingSubmit,
    OnboardingSubmitOut,
    PlayerGameEntry,
    ResumableGameOut,
    RoundPickSubmit,
    RoundResultOut,
    RoundStartOut,
)
from ..services.game_service import game_service

router = APIRouter(prefix="/api/game", tags=["game"])


@router.get("/categories", response_model=List[CategoryOut])
async def get_categories(
    db: AsyncSession = Depends(get_db),
):
    """List supported categories and available inventory counts."""
    return await game_service.get_categories(db)


@router.get("/leaderboard", response_model=List[LeaderboardEntry])
async def get_leaderboard(
    limit: int = 10,
    category: str = "fountain_pens",
    db: AsyncSession = Depends(get_db),
):
    """Return top completed games for a category."""
    try:
        return await game_service.get_leaderboard(db, limit=limit, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/player/{player_name}/history", response_model=List[PlayerGameEntry])
async def get_player_history(
    player_name: str,
    limit: int = 20,
    category: str = "fountain_pens",
    db: AsyncSession = Depends(get_db),
):
    """Return completed game history for one player/category."""
    try:
        return await game_service.get_player_history(db, player_name, limit=limit, category=category)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/start", response_model=GameOut)
async def start_game(
    payload: GameCreate,
    db: AsyncSession = Depends(get_db),
):
    """Create a new game session."""
    try:
        game = await game_service.create_game(
            db,
            player_name=payload.player_name,
            category=payload.category,
            total_rounds=5,
            fresh_start=payload.fresh_start,
        )
        return GameOut(**game)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/resume-state", response_model=ResumableGameOut)
async def get_resume_state(
    player_name: str,
    category: str = "fountain_pens",
    db: AsyncSession = Depends(get_db),
):
    """Return whether this player/category has an in-progress game."""
    try:
        result = await game_service.get_resume_state(db, player_name=player_name, category=category)
        return ResumableGameOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{game_id}/onboarding", response_model=OnboardingOut)
async def get_onboarding(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return onboarding pool for a game."""
    try:
        result = await game_service.get_onboarding(db, game_id)
        return OnboardingOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{game_id}/onboarding/submit", response_model=OnboardingSubmitOut)
async def submit_onboarding(
    game_id: str,
    payload: OnboardingSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit onboarding picks and 1..5 preference rating."""
    try:
        result = await game_service.submit_onboarding(
            db,
            game_id,
            selected_product_ids=payload.selected_product_ids,
            rating=payload.rating,
        )
        return OnboardingSubmitOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{game_id}/round/start", response_model=RoundStartOut)
async def start_round(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Start and return the next round candidate set."""
    try:
        result = await game_service.start_round(db, game_id)
        return RoundStartOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/{game_id}/round/{round_number}/pick", response_model=RoundResultOut)
async def submit_round_pick(
    game_id: str,
    round_number: int,
    payload: RoundPickSubmit,
    db: AsyncSession = Depends(get_db),
):
    """Submit one round pick and return AI-vs-human result payload."""
    try:
        result = await game_service.submit_pick(
            db,
            game_id,
            round_number,
            payload.product_id,
        )
        return RoundResultOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/{game_id}/status", response_model=GameStatusOut)
async def get_game_status(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return current status for a game session."""
    try:
        status = await game_service.get_game_status(db, game_id)
        return GameStatusOut(**status)
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/{game_id}/summary", response_model=GameSummaryOut)
async def get_game_summary(
    game_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Return final summary for a completed game session."""
    try:
        result = await game_service.get_game_summary(db, game_id)
        return GameSummaryOut(**result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
