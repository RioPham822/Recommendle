"""Static persona definitions used by admin-run simulations."""

from __future__ import annotations

from typing import Any


PERSONAS: list[dict[str, Any]] = [
    {
        "id": "action-thriller-mainstream",
        "category": "movies",
        "display_name": "Action Thriller Mainstream",
        "summary": "Prefers high-energy action and thriller movies with recognizable casts and modern pacing.",
        "hard_likes": {
            "genres": ["Action", "Thriller"],
        },
        "soft_likes": {
            "keywords": ["spy", "heist", "revenge", "survival", "mission"],
            "directors": ["Christopher Nolan", "Denis Villeneuve", "Chad Stahelski"],
        },
        "dislikes": {
            "genres": ["Romance"],
            "keywords": ["period drama", "musical"],
        },
        "numeric_preferences": {
            "release_year": {"min": 2000, "weight": 0.8},
            "runtime_minutes": {"min": 95, "max": 150, "weight": 0.7},
            "vote_average": {"min": 6.5, "weight": 0.6},
        },
        "behavior": {
            "onboarding_pick_count": 8,
            "onboarding_rating": 5,
            "exploration_rate": 0.08,
            "negative_feedback_rate": 0.3,
            "negative_feedback_threshold": -2.5,
        },
    },
    {
        "id": "psychological-thriller-dark",
        "category": "movies",
        "display_name": "Psychological Thriller Dark",
        "summary": "Likes tense, moody psychological thrillers and crime dramas with darker themes.",
        "hard_likes": {
            "genres": ["Thriller", "Crime"],
        },
        "soft_likes": {
            "keywords": ["murder", "obsession", "detective", "mind game", "serial killer"],
            "directors": ["David Fincher", "Martin Scorsese", "Bong Joon-ho"],
        },
        "dislikes": {
            "genres": ["Family", "Animation", "Romance"],
        },
        "numeric_preferences": {
            "release_year": {"min": 1995, "weight": 0.4},
            "runtime_minutes": {"min": 100, "max": 165, "weight": 0.5},
            "vote_average": {"min": 7.0, "weight": 0.8},
        },
        "behavior": {
            "onboarding_pick_count": 7,
            "onboarding_rating": 5,
            "exploration_rate": 0.05,
            "negative_feedback_rate": 0.4,
            "negative_feedback_threshold": -2.0,
        },
    },
    {
        "id": "feel-good-family-animation",
        "category": "movies",
        "display_name": "Feel-Good Family Animation",
        "summary": "Prefers upbeat family-friendly animation with adventure and humor.",
        "hard_likes": {
            "genres": ["Animation", "Family"],
        },
        "soft_likes": {
            "keywords": ["friendship", "adventure", "coming of age", "talking animal"],
            "production_companies": ["Pixar", "Disney", "DreamWorks"],
        },
        "dislikes": {
            "genres": ["Horror", "Crime"],
            "keywords": ["gore", "serial killer"],
        },
        "numeric_preferences": {
            "release_year": {"min": 1998, "weight": 0.4},
            "runtime_minutes": {"min": 75, "max": 125, "weight": 0.7},
            "vote_average": {"min": 6.0, "weight": 0.5},
        },
        "behavior": {
            "onboarding_pick_count": 6,
            "onboarding_rating": 4,
            "exploration_rate": 0.12,
            "negative_feedback_rate": 0.25,
            "negative_feedback_threshold": -2.4,
        },
    },
    {
        "id": "competitive-action-gamer",
        "category": "games",
        "display_name": "Competitive Action Gamer",
        "summary": "Prefers fast-paced action games with multiplayer or combat-heavy loops.",
        "hard_likes": {
            "genres": ["Shooter", "Fighting", "Hack and slash/Beat 'em up"],
            "game_modes": ["Multiplayer", "Co-operative"],
        },
        "soft_likes": {
            "themes": ["Action", "Warfare", "Science fiction"],
            "platforms": ["PC (Microsoft Windows)", "PlayStation 5", "Xbox Series X|S"],
        },
        "dislikes": {
            "genres": ["Point-and-click", "Visual Novel"],
            "themes": ["Romance"],
        },
        "numeric_preferences": {
            "release_year": {"min": 2015, "weight": 0.6},
            "total_rating": {"min": 70, "weight": 0.7},
            "hypes": {"min": 20, "weight": 0.3},
        },
        "behavior": {
            "onboarding_pick_count": 8,
            "onboarding_rating": 5,
            "exploration_rate": 0.1,
            "negative_feedback_rate": 0.35,
            "negative_feedback_threshold": -2.0,
        },
    },
    {
        "id": "cozy-strategy-builder",
        "category": "games",
        "display_name": "Cozy Strategy Builder",
        "summary": "Likes thoughtful strategy, simulation, and builder games with low-stress pacing.",
        "hard_likes": {
            "genres": ["Simulator", "Strategy", "Puzzle"],
        },
        "soft_likes": {
            "themes": ["Business", "Sandbox", "Fantasy"],
            "game_modes": ["Single player"],
            "player_perspectives": ["Bird view / Isometric", "Side view"],
        },
        "dislikes": {
            "genres": ["Shooter", "Fighting"],
            "themes": ["Horror", "Warfare"],
        },
        "numeric_preferences": {
            "release_year": {"min": 2010, "weight": 0.3},
            "total_rating": {"min": 72, "weight": 0.6},
        },
        "behavior": {
            "onboarding_pick_count": 7,
            "onboarding_rating": 4,
            "exploration_rate": 0.09,
            "negative_feedback_rate": 0.2,
            "negative_feedback_threshold": -2.2,
        },
    },
    {
        "id": "classic-premium-writer",
        "category": "fountain_pens",
        "display_name": "Classic Premium Writer",
        "summary": "Prefers premium, understated fountain pens from heritage brands with classic styling.",
        "hard_likes": {
            "vendor": ["Pilot", "Sailor", "Platinum", "Lamy"],
        },
        "soft_likes": {
            "product_type": ["Fountain Pen"],
            "tags": ["classic", "professional", "gold nib", "resin"],
            "nib_sizes": ["Fine", "Medium"],
        },
        "dislikes": {
            "tags": ["novelty", "glitter", "oversized"],
        },
        "numeric_preferences": {
            "price_min": {"min": 80, "max": 400, "weight": 0.7},
        },
        "behavior": {
            "onboarding_pick_count": 6,
            "onboarding_rating": 5,
            "exploration_rate": 0.06,
            "negative_feedback_rate": 0.15,
            "negative_feedback_threshold": -1.8,
        },
    },
]


def list_personas() -> list[dict[str, Any]]:
    """Return all bundled persona definitions."""
    return [dict(persona) for persona in PERSONAS]


def get_persona(persona_id: str) -> dict[str, Any]:
    """Look up one persona by id."""
    for persona in PERSONAS:
        if persona["id"] == persona_id:
            return dict(persona)
    raise KeyError(persona_id)
