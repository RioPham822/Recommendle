"""Admin persona simulation orchestration and canonical persona profile management."""

from __future__ import annotations

import asyncio
import random
from datetime import datetime
from typing import Any

from fastapi.encoders import jsonable_encoder
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import GameRecord, PersonaProfileRecord, PersonaSimulationRunRecord, get_session_factory
from ..personas import get_persona, list_personas
from ..schemas_persona import PersonaDefinitionOut
from .game_service import game_service


LIST_LIKE_FIELDS = {
    "genres",
    "keywords",
    "production_companies",
    "directors",
    "themes",
    "game_modes",
    "player_perspectives",
    "platforms",
    "nib_sizes",
    "tags",
}
TERMINAL_RUN_STATUSES = {"completed", "failed", "max_rounds_reached", "superseded"}


class PersonaSimulationService:
    """Launch and track background persona simulations."""

    def __init__(self) -> None:
        self._session_factory = get_session_factory()
        self._tasks: dict[str, asyncio.Task[Any]] = {}

    @staticmethod
    def _now() -> datetime:
        return datetime.utcnow()

    @staticmethod
    def _persona_player_name(run_id: str, persona: dict[str, Any]) -> str:
        label = str(persona.get("display_name") or persona.get("id") or "persona")
        return f"[Persona] {label} [{run_id[:8]}]"

    @staticmethod
    def _normalized_text(value: Any) -> str:
        return str(value or "").strip().lower()

    @staticmethod
    def _is_terminal_status(status: str | None) -> bool:
        return str(status or "").strip().lower() in TERMINAL_RUN_STATUSES

    def _extract_values(self, product: dict[str, Any], field: str) -> list[str]:
        value = product.get(field)
        if value is None:
            return []
        if isinstance(value, list):
            return [self._normalized_text(item) for item in value if self._normalized_text(item)]
        if isinstance(value, tuple):
            return [self._normalized_text(item) for item in value if self._normalized_text(item)]
        if isinstance(value, str):
            text = self._normalized_text(value)
            if not text:
                return []
            if field in LIST_LIKE_FIELDS and "|" in text:
                return [part.strip() for part in text.split("|") if part.strip()]
            return [text]
        return [self._normalized_text(value)]

    def _score_signal_group(
        self,
        product: dict[str, Any],
        fields: dict[str, list[str]],
        *,
        weight: float,
        matched_signals: list[str],
        positive: bool,
    ) -> float:
        score = 0.0
        for field, desired_values in (fields or {}).items():
            product_values = set(self._extract_values(product, field))
            if not product_values:
                continue
            for desired in desired_values or []:
                normalized = self._normalized_text(desired)
                if not normalized:
                    continue
                if any(normalized in candidate or candidate in normalized for candidate in product_values):
                    score += weight if positive else -weight
                    matched_signals.append(f"{field}: {desired}")
        return score

    def _score_numeric_preferences(
        self,
        product: dict[str, Any],
        numeric_preferences: dict[str, dict[str, float]],
        matched_signals: list[str],
    ) -> float:
        score = 0.0
        for field, config in (numeric_preferences or {}).items():
            raw_value = product.get(field)
            try:
                value = float(raw_value)
            except (TypeError, ValueError):
                continue
            weight = float(config.get("weight", 0.5))
            min_value = config.get("min")
            max_value = config.get("max")
            if min_value is not None and value < float(min_value):
                score -= weight
                continue
            if max_value is not None and value > float(max_value):
                score -= weight
                continue
            score += weight
            if min_value is not None or max_value is not None:
                if min_value is not None and max_value is not None:
                    matched_signals.append(f"{field}: {value:g} in [{float(min_value):g}, {float(max_value):g}]")
                elif min_value is not None:
                    matched_signals.append(f"{field}: {value:g} >= {float(min_value):g}")
                else:
                    matched_signals.append(f"{field}: {value:g} <= {float(max_value):g}")
        return score

    def score_product(
        self,
        persona: dict[str, Any],
        product: dict[str, Any],
        *,
        randomizer: random.Random | None = None,
    ) -> tuple[float, list[str]]:
        matched_signals: list[str] = []
        score = 0.0
        score += self._score_signal_group(
            product,
            persona.get("hard_likes") or {},
            weight=3.0,
            matched_signals=matched_signals,
            positive=True,
        )
        score += self._score_signal_group(
            product,
            persona.get("soft_likes") or {},
            weight=1.4,
            matched_signals=matched_signals,
            positive=True,
        )
        score += self._score_signal_group(
            product,
            persona.get("dislikes") or {},
            weight=2.1,
            matched_signals=matched_signals,
            positive=False,
        )
        score += self._score_numeric_preferences(
            product,
            persona.get("numeric_preferences") or {},
            matched_signals,
        )
        exploration_rate = float((persona.get("behavior") or {}).get("exploration_rate") or 0.0)
        if randomizer is not None and exploration_rate > 0:
            score += randomizer.uniform(-exploration_rate, exploration_rate)
        return score, matched_signals[:6]

    @staticmethod
    def _behavior_value(persona: dict[str, Any], key: str, default: Any) -> Any:
        return (persona.get("behavior") or {}).get(key, default)

    def _seed_payload(self, persona: dict[str, Any]) -> dict[str, Any]:
        likes = {}
        dislikes = {}
        for field, values in (persona.get("hard_likes") or {}).items():
            likes[field] = list(values or [])[:4]
        for field, values in (persona.get("soft_likes") or {}).items():
            existing = list(likes.get(field) or [])
            likes[field] = (existing + list(values or []))[:6]
        for field, values in (persona.get("dislikes") or {}).items():
            dislikes[field] = list(values or [])[:5]
        return {
            "likes": likes,
            "dislikes": dislikes,
            "like_product_ids": [],
            "dislike_product_ids": [],
        }

    async def _active_profile(self, db: AsyncSession, persona_id: str) -> PersonaProfileRecord | None:
        return await db.scalar(select(PersonaProfileRecord).where(PersonaProfileRecord.persona_id == persona_id))

    async def _supersede_existing_runs(self, db: AsyncSession, persona_id: str) -> None:
        rows = (
            await db.execute(
                select(PersonaSimulationRunRecord).where(
                    PersonaSimulationRunRecord.persona_id == persona_id,
                    PersonaSimulationRunRecord.status.in_(["queued", "starting", "seeding", "onboarding", "running"]),
                )
            )
        ).scalars().all()
        if not rows:
            return
        now = self._now()
        for row in rows:
            row.status = "superseded"
            row.error_message = None
            metrics = dict(row.metrics or {})
            metrics["latest_message"] = "Superseded by a newer admin refresh"
            row.metrics = metrics
            events = list(row.events or [])
            events.append(
                jsonable_encoder(
                    {
                        "type": "status",
                        "timestamp": now,
                        "title": "Run superseded",
                        "detail": "A newer admin refresh for this persona was launched.",
                    }
                )
            )
            row.events = events[-200:]
            row.completed_at = now
            row.updated_at = now
            task = self._tasks.pop(row.id, None)
            if task is not None and not task.done():
                task.cancel()
        await db.commit()

    async def _update_run(
        self,
        run_id: str,
        *,
        status: str | None = None,
        game_id: str | None = None,
        latest_message: str | None = None,
        metrics_updates: dict[str, Any] | None = None,
        append_event: dict[str, Any] | None = None,
        error_message: str | None = None,
        started: bool = False,
        completed: bool = False,
        final_summary: dict[str, Any] | None = None,
        game_status: dict[str, Any] | None = None,
    ) -> None:
        async with self._session_factory() as db:
            run_row = await db.scalar(select(PersonaSimulationRunRecord).where(PersonaSimulationRunRecord.id == run_id))
            if run_row is None:
                return
            now = self._now()
            if status is not None:
                run_row.status = status
            if game_id is not None:
                run_row.game_id = game_id
            metrics = dict(run_row.metrics or {})
            if latest_message is not None:
                metrics["latest_message"] = latest_message
            if metrics_updates:
                metrics.update(jsonable_encoder(metrics_updates))
            if game_status is not None:
                metrics["game_status"] = jsonable_encoder(game_status)
            if final_summary is not None:
                metrics["final_summary"] = jsonable_encoder(final_summary)
            run_row.metrics = metrics
            if append_event:
                events = list(run_row.events or [])
                events.append(jsonable_encoder(append_event))
                run_row.events = events[-200:]
            if error_message is not None:
                run_row.error_message = error_message
            if started and run_row.started_at is None:
                run_row.started_at = now
            if completed:
                run_row.completed_at = now
            run_row.updated_at = now
            await db.commit()

    async def _apply_match_target(self, db: AsyncSession, game_id: str, target: int) -> None:
        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == game_id))
        if game_row is None:
            raise ValueError("Game not found for persona run")
        state = game_service._ensure_redesign_state(game_row.model_state or {})
        state["match_streak_target"] = int(target)
        game_row.model_state = state
        game_row.total_rounds = int(target)
        game_row.updated_at = self._now()
        await db.commit()

    async def _build_product_lookup(
        self,
        db: AsyncSession,
        category: str,
        ids: list[str],
    ) -> dict[str, dict[str, Any]]:
        docs = await game_service._get_products_by_ids(
            db,
            ids,
            projection=game_service._card_projection(category) | game_service._feature_projection(category),
        )
        return {str(doc["_id"]): doc for doc in docs}

    async def _choose_onboarding_picks(
        self,
        db: AsyncSession,
        persona: dict[str, Any],
        category: str,
        pool_ids: list[str],
        *,
        randomizer: random.Random,
    ) -> tuple[list[str], list[dict[str, Any]]]:
        products_by_id = await self._build_product_lookup(db, category, pool_ids)
        scored: list[tuple[str, float, list[str], str]] = []
        for product_id in pool_ids:
            product = products_by_id.get(product_id)
            if product is None:
                continue
            score, signals = self.score_product(persona, product, randomizer=randomizer)
            scored.append((product_id, score, signals, str(product.get("title") or "Untitled")))
        scored.sort(key=lambda item: item[1], reverse=True)
        pick_count = int(self._behavior_value(persona, "onboarding_pick_count", 6))
        pick_count = max(game_service.MIN_ONBOARDING_SELECTIONS, min(game_service.MAX_ONBOARDING_SELECTIONS, pick_count))
        chosen = scored[:pick_count]
        return [item[0] for item in chosen], [
            {
                "product_id": item[0],
                "title": item[3],
                "persona_score": round(item[1], 3),
                "matched_signals": item[2],
            }
            for item in chosen
        ]

    async def _refresh_canonical_profile(
        self,
        db: AsyncSession,
        *,
        run_id: str,
        game_id: str,
        persona: dict[str, Any],
        summary: dict[str, Any],
    ) -> None:
        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == game_id))
        if game_row is None:
            raise ValueError("Completed game not found for persona profile refresh")
        profile_row = await self._active_profile(db, str(persona["id"]))
        if profile_row is None:
            profile_row = PersonaProfileRecord(persona_id=str(persona["id"]))
            db.add(profile_row)
        profile_row.persona_name = str(persona["display_name"])
        profile_row.category = str(persona["category"])
        profile_row.source_run_id = run_id
        profile_row.source_game_id = game_id
        profile_row.persona_snapshot = jsonable_encoder(persona)
        profile_row.model_state = jsonable_encoder(game_row.model_state or {})
        profile_row.onboarding_selected_ids = list(game_row.onboarding_selected_ids or [])
        profile_row.onboarding_rating = game_row.onboarding_rating
        profile_row.rounds_to_complete = int(summary.get("rounds_played") or 0)
        profile_row.match_rate = float(summary.get("match_rate") or 0.0)
        profile_row.longest_match_streak = int(summary.get("longest_match_streak") or 0)
        profile_row.completed_at = game_row.updated_at or self._now()
        profile_row.updated_at = self._now()
        await db.commit()

    async def _run_simulation(self, run_id: str) -> None:
        randomizer = random.Random(run_id)
        async with self._session_factory() as db:
            run_row = await db.scalar(select(PersonaSimulationRunRecord).where(PersonaSimulationRunRecord.id == run_id))
            if run_row is None or run_row.status == "superseded":
                return
            persona = dict(run_row.persona_snapshot or {})
            config = dict(run_row.config or {})
            match_target = int(config.get("match_streak_target") or 5)
            max_rounds = int(config.get("max_rounds") or 40)
            player_name = self._persona_player_name(run_id, persona)

            await self._update_run(
                run_id,
                status="starting",
                started=True,
                latest_message="Creating persona game session",
                append_event={
                    "type": "status",
                    "timestamp": self._now(),
                    "title": "Simulation started",
                    "detail": f"Launching {persona.get('display_name')} in {persona.get('category')}",
                },
            )
            game = await game_service.create_game(
                db,
                player_name=player_name,
                category=str(persona.get("category") or "movies"),
                mode="beta",
                fresh_start=True,
            )
            game_id = str(game["id"])
            await self._apply_match_target(db, game_id, match_target)

            seed_payload = self._seed_payload(persona)
            await self._update_run(
                run_id,
                status="seeding",
                game_id=game_id,
                latest_message="Applying persona seed preferences",
                metrics_updates={
                    "current_round": 0,
                    "rounds_played": 0,
                    "current_match_streak": 0,
                    "longest_match_streak": 0,
                    "match_streak_target": match_target,
                    "total_matches": 0,
                },
                append_event={
                    "type": "seed",
                    "timestamp": self._now(),
                    "title": "Seed preferences applied",
                    "detail": "Used persona likes and dislikes to bias the beta-mode run.",
                    "data": seed_payload,
                },
            )
            await game_service.submit_seed_preferences(
                db,
                game_id,
                likes=seed_payload["likes"],
                dislikes=seed_payload["dislikes"],
                like_product_ids=seed_payload["like_product_ids"],
                dislike_product_ids=seed_payload["dislike_product_ids"],
            )

            onboarding = await game_service.get_onboarding(db, game_id)
            category = str(onboarding["category"])
            selected_ids, onboarding_details = await self._choose_onboarding_picks(
                db,
                persona,
                category,
                [str(product["id"]) for product in onboarding["products"]],
                randomizer=randomizer,
            )
            onboarding_rating = int(self._behavior_value(persona, "onboarding_rating", 5))
            await self._update_run(
                run_id,
                status="onboarding",
                latest_message="Submitting onboarding selections",
                append_event={
                    "type": "onboarding",
                    "timestamp": self._now(),
                    "title": "Onboarding selections made",
                    "detail": f"Selected {len(selected_ids)} products from the onboarding pool.",
                    "data": {
                        "selected_count": len(selected_ids),
                        "rating": onboarding_rating,
                        "choices": onboarding_details,
                    },
                },
            )
            await game_service.submit_onboarding(
                db,
                game_id,
                selected_product_ids=selected_ids,
                rating=onboarding_rating,
            )

            last_result: dict[str, Any] | None = None
            game_status_payload: dict[str, Any] | None = None
            for _ in range(max_rounds):
                latest_run_row = await db.scalar(select(PersonaSimulationRunRecord).where(PersonaSimulationRunRecord.id == run_id))
                if latest_run_row is None or latest_run_row.status == "superseded":
                    return
                round_payload = await game_service.start_round(db, game_id)
                round_number = int(round_payload["round_number"])
                candidate_ids = [str(candidate["id"]) for candidate in round_payload["candidates"]]
                products_by_id = await self._build_product_lookup(db, category, candidate_ids)
                scored_candidates: list[tuple[str, float, list[str], str]] = []
                for candidate_id in candidate_ids:
                    product = products_by_id.get(candidate_id)
                    if product is None:
                        continue
                    score, signals = self.score_product(persona, product, randomizer=randomizer)
                    scored_candidates.append((candidate_id, score, signals, str(product.get("title") or "Untitled")))
                scored_candidates.sort(key=lambda item: item[1], reverse=True)
                if not scored_candidates:
                    raise ValueError("Persona simulation could not score any round candidates")
                chosen_id, chosen_score, chosen_signals, chosen_title = scored_candidates[0]
                negative_threshold = float(self._behavior_value(persona, "negative_feedback_threshold", -2.0))
                negative_rate = float(self._behavior_value(persona, "negative_feedback_rate", 0.0))
                less_like_ids = [
                    candidate_id
                    for candidate_id, score, _, _ in scored_candidates[-2:]
                    if score <= negative_threshold and randomizer.random() <= negative_rate
                ]

                await self._update_run(
                    run_id,
                    status="running",
                    latest_message=f"Playing round {round_number}",
                    metrics_updates={"current_round": round_number},
                )
                result = await game_service.submit_pick(
                    db,
                    game_id,
                    round_number,
                    chosen_id,
                    less_like_ids=less_like_ids,
                )
                last_result = result
                game_status_payload = await game_service.get_game_status(db, game_id)
                await self._update_run(
                    run_id,
                    status="running" if not result["game_complete"] else "completed",
                    latest_message=(
                        f"Completed in {result['rounds_played']} rounds"
                        if result["game_complete"]
                        else f"Round {round_number} complete"
                    ),
                    metrics_updates={
                        "current_round": round_number,
                        "rounds_played": int(result.get("rounds_played") or 0),
                        "current_match_streak": int(result.get("current_match_streak") or 0),
                        "longest_match_streak": int(result.get("longest_match_streak") or 0),
                        "match_streak_target": int(result.get("match_streak_target") or match_target),
                        "total_matches": int(result.get("total_matches") or 0),
                        "human_score": int(result.get("total_human_score") or 0),
                        "ai_score": int(result.get("total_ai_score") or 0),
                        "score_difference": int(result.get("total_human_score") or 0) - int(result.get("total_ai_score") or 0),
                    },
                    game_status=game_status_payload,
                    append_event={
                        "type": "round",
                        "timestamp": self._now(),
                        "title": f"Round {round_number}: {chosen_title}",
                        "detail": (
                            f"Persona chose {chosen_title}. AI rank of pick: {result.get('ai_rank_of_pick')}. "
                            f"Streak is now {result.get('current_match_streak')}."
                        ),
                        "round_number": round_number,
                        "data": {
                            "chosen_product_id": chosen_id,
                            "chosen_title": chosen_title,
                            "persona_score": round(chosen_score, 3),
                            "matched_signals": chosen_signals,
                            "less_like_ids": less_like_ids,
                            "ai_pick_title": result.get("ai_pick", {}).get("title"),
                            "ai_rank_of_pick": result.get("ai_rank_of_pick"),
                            "preference_match": bool(result.get("preference_match")),
                            "current_match_streak": int(result.get("current_match_streak") or 0),
                        },
                    },
                )
                if result["game_complete"]:
                    break

            if last_result and last_result.get("game_complete"):
                summary = await game_service.get_game_summary(db, game_id)
                await self._refresh_canonical_profile(
                    db,
                    run_id=run_id,
                    game_id=game_id,
                    persona=persona,
                    summary=summary,
                )
                await self._update_run(
                    run_id,
                    status="completed",
                    latest_message=f"Finished after {summary.get('rounds_played')} rounds",
                    metrics_updates={
                        "rounds_played": int(summary.get("rounds_played") or 0),
                        "current_match_streak": int(summary.get("current_match_streak") or 0),
                        "longest_match_streak": int(summary.get("longest_match_streak") or 0),
                        "match_streak_target": int(summary.get("match_streak_target") or match_target),
                        "total_matches": int(summary.get("total_matches") or 0),
                        "human_score": int(summary.get("human_score") or 0),
                        "ai_score": int(summary.get("ai_score") or 0),
                        "score_difference": int(summary.get("human_score") or 0) - int(summary.get("ai_score") or 0),
                        "match_rate": float(summary.get("match_rate") or 0.0),
                    },
                    game_status=await game_service.get_game_status(db, game_id),
                    final_summary=summary,
                    append_event={
                        "type": "summary",
                        "timestamp": self._now(),
                        "title": "Simulation completed",
                        "detail": (
                            f"Reached the target streak of {summary.get('match_streak_target')} "
                            f"in {summary.get('rounds_played')} rounds."
                        ),
                        "data": {
                            "rounds_played": summary.get("rounds_played"),
                            "match_rate": summary.get("match_rate"),
                            "human_score": summary.get("human_score"),
                            "ai_score": summary.get("ai_score"),
                        },
                    },
                    completed=True,
                )
            else:
                partial_status = game_status_payload or await game_service.get_game_status(db, game_id)
                await self._update_run(
                    run_id,
                    status="max_rounds_reached",
                    latest_message=f"Stopped after {max_rounds} rounds without reaching the target streak",
                    metrics_updates={
                        "rounds_played": int(partial_status.get("rounds_played") or 0),
                        "current_match_streak": int(partial_status.get("current_match_streak") or 0),
                        "longest_match_streak": int(partial_status.get("longest_match_streak") or 0),
                        "match_streak_target": int(partial_status.get("match_streak_target") or match_target),
                        "total_matches": int(partial_status.get("current_match_streak") or 0),
                        "human_score": int(partial_status.get("human_score") or 0),
                        "ai_score": int(partial_status.get("ai_score") or 0),
                        "score_difference": int(partial_status.get("human_score") or 0) - int(partial_status.get("ai_score") or 0),
                    },
                    game_status=partial_status,
                    append_event={
                        "type": "summary",
                        "timestamp": self._now(),
                        "title": "Max rounds reached",
                        "detail": f"The run stopped after {max_rounds} rounds without hitting the streak target.",
                    },
                    completed=True,
                )

    async def _execute_run(self, run_id: str) -> None:
        try:
            await self._run_simulation(run_id)
        except asyncio.CancelledError:  # pragma: no cover
            return
        except Exception as exc:  # pragma: no cover
            await self._update_run(
                run_id,
                status="failed",
                latest_message="Simulation failed",
                error_message=str(exc),
                append_event={
                    "type": "error",
                    "timestamp": self._now(),
                    "title": "Simulation failed",
                    "detail": str(exc),
                },
                completed=True,
            )
        finally:
            self._tasks.pop(run_id, None)

    async def list_persona_definitions(self) -> list[PersonaDefinitionOut]:
        return [PersonaDefinitionOut(**persona) for persona in list_personas()]

    async def list_public_personas(self, *, category: str | None = None) -> list[dict[str, Any]]:
        """Return only personas that have a completed canonical playable profile."""
        async with self._session_factory() as db:
            stmt = select(PersonaProfileRecord)
            if category:
                stmt = stmt.where(PersonaProfileRecord.category == str(category))
            rows = (await db.execute(stmt.order_by(PersonaProfileRecord.updated_at.desc()))).scalars().all()
            return [
                {
                    "id": row.persona_id,
                    "category": row.category,
                    "display_name": row.persona_name,
                    "summary": str((row.persona_snapshot or {}).get("summary") or ""),
                    "rounds_to_complete": int(row.rounds_to_complete or 0),
                    "match_rate": float(row.match_rate or 0.0),
                    "last_refreshed_at": row.updated_at,
                }
                for row in rows
            ]

    async def prepare_game_from_persona(
        self,
        db: AsyncSession,
        *,
        game_id: str,
        persona_id: str,
    ) -> dict[str, Any]:
        """Copy a canonical persona profile into a fresh user game and skip onboarding."""
        profile_row = await self._active_profile(db, persona_id)
        if profile_row is None:
            raise ValueError("This persona is not ready yet. Ask an admin to refresh it first.")
        selected_ids = list(profile_row.onboarding_selected_ids or [])
        if not game_service.MIN_ONBOARDING_SELECTIONS <= len(selected_ids) <= game_service.MAX_ONBOARDING_SELECTIONS:
            raise ValueError(
                "This persona profile is incomplete. Ask an admin to refresh it before players use it."
            )
        game_row = await db.scalar(select(GameRecord).where(GameRecord.id == game_id))
        if game_row is None:
            raise ValueError("Game not found")
        copied_state = game_service._reset_run_progress(profile_row.model_state or {})
        game_row.status = "ready"
        game_row.current_round = 0
        game_row.human_score = 0
        game_row.ai_score = 0
        game_row.model_state = jsonable_encoder(copied_state)
        game_row.onboarding_pool_ids = list(selected_ids)
        game_row.onboarding_selected_ids = list(selected_ids)
        game_row.onboarding_rating = profile_row.onboarding_rating
        game_row.total_rounds = int(
            copied_state.get("match_streak_target") or game_service.DEFAULT_MATCH_STREAK_TARGET
        )
        game_row.updated_at = self._now()
        await db.commit()
        return {
            "persona_id": profile_row.persona_id,
            "persona_name": profile_row.persona_name,
            "onboarding_selected_ids": list(selected_ids),
        }

    async def launch_run(
        self,
        db: AsyncSession,
        *,
        persona_id: str,
        match_streak_target: int,
        max_rounds: int,
    ) -> dict[str, Any]:
        """Create and enqueue a background persona simulation, superseding older live runs for the same persona."""
        persona = get_persona(persona_id)
        await self._supersede_existing_runs(db, str(persona["id"]))
        now = self._now()
        run_row = PersonaSimulationRunRecord(
            persona_id=str(persona["id"]),
            persona_name=str(persona["display_name"]),
            category=str(persona["category"]),
            status="queued",
            config={
                "match_streak_target": int(match_streak_target),
                "max_rounds": int(max_rounds),
            },
            persona_snapshot=jsonable_encoder(persona),
            metrics={
                "current_round": 0,
                "rounds_played": 0,
                "current_match_streak": 0,
                "longest_match_streak": 0,
                "match_streak_target": int(match_streak_target),
                "total_matches": 0,
                "latest_message": "Queued for execution",
            },
            created_at=now,
            updated_at=now,
        )
        db.add(run_row)
        await db.commit()
        await db.refresh(run_row)
        self._tasks[run_row.id] = asyncio.create_task(self._execute_run(run_row.id))
        return await self.get_run_detail(db, run_row.id)

    async def list_runs(self, db: AsyncSession, *, limit: int = 40) -> list[dict[str, Any]]:
        rows = (
            await db.execute(
                select(PersonaSimulationRunRecord)
                .order_by(PersonaSimulationRunRecord.created_at.desc())
                .limit(max(limit * 4, limit))
            )
        ).scalars().all()
        profile_ids = set(
            (
                await db.execute(select(PersonaProfileRecord.persona_id))
            ).scalars().all()
        )
        latest_by_persona: dict[str, PersonaSimulationRunRecord] = {}
        for row in rows:
            if row.persona_id in latest_by_persona:
                continue
            latest_by_persona[row.persona_id] = row
            if len(latest_by_persona) >= limit:
                break
        unique_rows = list(latest_by_persona.values())
        return [self._run_list_payload(row, has_active_profile=row.persona_id in profile_ids) for row in unique_rows]

    def _run_list_payload(self, row: PersonaSimulationRunRecord, *, has_active_profile: bool = False) -> dict[str, Any]:
        metrics = dict(row.metrics or {})
        return {
            "id": row.id,
            "persona_id": row.persona_id,
            "persona_name": row.persona_name,
            "category": row.category,
            "status": row.status,
            "game_id": row.game_id,
            "created_at": row.created_at,
            "updated_at": row.updated_at,
            "started_at": row.started_at,
            "completed_at": row.completed_at,
            "current_round": int(metrics.get("current_round") or 0),
            "rounds_played": int(metrics.get("rounds_played") or 0),
            "current_match_streak": int(metrics.get("current_match_streak") or 0),
            "longest_match_streak": int(metrics.get("longest_match_streak") or 0),
            "match_streak_target": int(metrics.get("match_streak_target") or 5),
            "total_matches": int(metrics.get("total_matches") or 0),
            "latest_message": str(metrics.get("latest_message") or ""),
            "error_message": row.error_message,
            "has_active_profile": bool(has_active_profile),
            "metrics": {
                key: value
                for key, value in metrics.items()
                if key not in {"game_status", "final_summary", "latest_message"}
            },
        }

    async def get_run_detail(self, db: AsyncSession, run_id: str) -> dict[str, Any]:
        row = await db.scalar(select(PersonaSimulationRunRecord).where(PersonaSimulationRunRecord.id == run_id))
        if row is None:
            raise ValueError("Persona simulation run not found")
        profile_row = await self._active_profile(db, row.persona_id)
        payload = self._run_list_payload(row, has_active_profile=profile_row is not None)
        metrics = dict(row.metrics or {})
        persona_snapshot = dict(row.persona_snapshot or {})
        if not persona_snapshot:
            persona_snapshot = get_persona(row.persona_id)
        payload.update(
            {
                "config": dict(row.config or {}),
                "persona": PersonaDefinitionOut(**persona_snapshot),
                "events": list(row.events or []),
                "game_status": metrics.get("game_status"),
                "final_summary": metrics.get("final_summary"),
            }
        )
        return payload


persona_simulation_service = PersonaSimulationService()
