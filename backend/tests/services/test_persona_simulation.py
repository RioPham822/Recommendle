import unittest
from datetime import datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from app.services.persona_simulation import PersonaSimulationService


class _FakeDB:
    def __init__(self, scalar_values=None):
        self.scalar_values = list(scalar_values or [])
        self.commit_calls = 0

    async def scalar(self, _stmt):
        if self.scalar_values:
            return self.scalar_values.pop(0)
        return None

    async def commit(self):
        self.commit_calls += 1


class _FixedRandom:
    def __init__(self, value):
        self.value = value

    def uniform(self, _low, _high):
        return self.value


class PersonaSimulationServiceTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.service = PersonaSimulationService()

    def test_extract_values_normalizes_lists_tuples_strings_and_scalars(self):
        self.assertEqual(self.service._extract_values({"genres": [" Action ", "", "Thriller"]}, "genres"), ["action", "thriller"])
        self.assertEqual(self.service._extract_values({"genres": (" Crime ", None)}, "genres"), ["crime"])
        self.assertEqual(self.service._extract_values({"genres": "Action | Thriller "}, "genres"), ["action", "thriller"])
        self.assertEqual(self.service._extract_values({"title": " Arrival "}, "title"), ["arrival"])
        self.assertEqual(self.service._extract_values({"vote_average": 8.5}, "vote_average"), ["8.5"])
        self.assertEqual(self.service._extract_values({}, "genres"), [])

    def test_score_product_combines_signals_numeric_preferences_and_exploration(self):
        persona = {
            "hard_likes": {"genres": ["Action", "Thriller"]},
            "soft_likes": {"keywords": ["Spy", "Mission"], "directors": ["Nolan"]},
            "dislikes": {"genres": ["Romance"]},
            "numeric_preferences": {
                "release_year": {"min": 2000, "weight": 0.8},
                "runtime_minutes": {"min": 90, "max": 150, "weight": 0.7},
                "vote_average": {"min": 7.0, "weight": 0.6},
            },
            "behavior": {"exploration_rate": 0.2},
        }
        product = {
            "genres": ["Action", "Thriller", "Romance"],
            "keywords": ["spy thriller", "mission impossible", "extra-1", "extra-2"],
            "directors": ["Christopher Nolan"],
            "release_year": 2014,
            "runtime_minutes": 130,
            "vote_average": 8.1,
        }

        score, signals = self.service.score_product(persona, product, randomizer=_FixedRandom(0.15))

        self.assertAlmostEqual(score, 10.35, places=5)
        self.assertEqual(len(signals), 6)
        self.assertIn("genres: Action", signals)
        self.assertIn("genres: Thriller", signals)
        self.assertIn("keywords: Spy", signals)
        self.assertIn("directors: Nolan", signals)

    def test_seed_payload_merges_and_truncates_likes_and_dislikes(self):
        payload = self.service._seed_payload(
            {
                "hard_likes": {"genres": ["A", "B", "C", "D", "E"]},
                "soft_likes": {"genres": ["F", "G"], "keywords": ["k1", "k2"]},
                "dislikes": {"genres": ["x1", "x2", "x3", "x4", "x5", "x6"]},
            }
        )

        self.assertEqual(payload["likes"]["genres"], ["A", "B", "C", "D", "F", "G"])
        self.assertEqual(payload["likes"]["keywords"], ["k1", "k2"])
        self.assertEqual(payload["dislikes"]["genres"], ["x1", "x2", "x3", "x4", "x5"])
        self.assertEqual(payload["like_product_ids"], [])
        self.assertEqual(payload["dislike_product_ids"], [])

    async def test_choose_onboarding_picks_sorts_by_score_and_clamps_pick_count(self):
        persona = {"behavior": {"onboarding_pick_count": 99}}
        pool_ids = ["p1", "p2", "p3"]
        products = {
            "p1": {"title": "Midnight Run"},
            "p2": {"title": "Arrival"},
            "p3": {"title": "Brick"},
        }

        with patch.object(self.service, "_build_product_lookup", AsyncMock(return_value=products)):
            with patch.object(
                self.service,
                "score_product",
                side_effect=[
                    (2.0, ["signal-1"]),
                    (4.5, ["signal-2"]),
                    (3.0, ["signal-3"]),
                ],
            ):
                chosen_ids, details = await self.service._choose_onboarding_picks(
                    db=object(),
                    persona=persona,
                    category="movies",
                    pool_ids=pool_ids,
                    randomizer=_FixedRandom(0.0),
                )

        self.assertEqual(chosen_ids, ["p2", "p3", "p1"])
        self.assertEqual(details[0]["title"], "Arrival")
        self.assertEqual(details[0]["matched_signals"], ["signal-2"])
        self.assertEqual(details[0]["persona_score"], 4.5)

    async def test_list_persona_definitions_returns_schema_models(self):
        result = await self.service.list_persona_definitions()

        self.assertGreater(len(result), 0)
        self.assertEqual(result[0].id, "action-thriller-mainstream")

    def test_run_list_payload_filters_internal_metrics(self):
        row = SimpleNamespace(
            id="run-1",
            persona_id="persona-1",
            persona_name="Persona One",
            category="movies",
            status="running",
            game_id="game-1",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 1, 12, 5, 0),
            started_at=None,
            completed_at=None,
            metrics={
                "current_round": 2,
                "rounds_played": 2,
                "current_match_streak": 1,
                "longest_match_streak": 1,
                "match_streak_target": 5,
                "total_matches": 1,
                "latest_message": "Running",
                "game_status": {"status": "ready"},
                "final_summary": {"rounds_played": 2},
                "human_score": 4,
            },
            error_message=None,
        )

        payload = self.service._run_list_payload(row, has_active_profile=True)

        self.assertEqual(payload["latest_message"], "Running")
        self.assertTrue(payload["has_active_profile"])
        self.assertEqual(payload["metrics"], {"current_round": 2, "rounds_played": 2, "current_match_streak": 1, "longest_match_streak": 1, "match_streak_target": 5, "total_matches": 1, "human_score": 4})

    async def test_prepare_game_from_persona_rejects_missing_or_incomplete_profiles(self):
        with self.assertRaises(ValueError) as missing:
            await self.service.prepare_game_from_persona(db=_FakeDB([None]), game_id="game-1", persona_id="persona-1")
        self.assertIn("not ready yet", str(missing.exception))

        incomplete_profile = SimpleNamespace(
            onboarding_selected_ids=[],
            model_state={},
            onboarding_rating=4,
            persona_id="persona-1",
            persona_name="Persona One",
        )
        with self.assertRaises(ValueError) as incomplete:
            await self.service.prepare_game_from_persona(
                db=_FakeDB([incomplete_profile]),
                game_id="game-1",
                persona_id="persona-1",
            )
        self.assertIn("incomplete", str(incomplete.exception))

    async def test_prepare_game_from_persona_copies_profile_into_game(self):
        profile = SimpleNamespace(
            onboarding_selected_ids=["p1", "p2"],
            model_state={"match_streak_target": 7, "seed_preferences": {"likes": {}}},
            onboarding_rating=5,
            persona_id="persona-1",
            persona_name="Persona One",
        )
        game_row = SimpleNamespace(
            id="game-1",
            status="onboarding",
            current_round=3,
            human_score=9,
            ai_score=7,
            model_state={},
            onboarding_pool_ids=[],
            onboarding_selected_ids=[],
            onboarding_rating=None,
            total_rounds=0,
            updated_at=None,
        )
        db = _FakeDB([profile, game_row])

        with patch.object(self.service, "_now", return_value=datetime(2026, 1, 2, 12, 0, 0)):
            with patch("app.services.persona_simulation.game_service._reset_run_progress", return_value={"match_streak_target": 7, "copied": True}):
                result = await self.service.prepare_game_from_persona(
                    db=db,
                    game_id="game-1",
                    persona_id="persona-1",
                )

        self.assertEqual(result["persona_id"], "persona-1")
        self.assertEqual(game_row.status, "ready")
        self.assertEqual(game_row.current_round, 0)
        self.assertEqual(game_row.human_score, 0)
        self.assertEqual(game_row.ai_score, 0)
        self.assertEqual(game_row.model_state["copied"], True)
        self.assertEqual(game_row.onboarding_pool_ids, ["p1", "p2"])
        self.assertEqual(game_row.onboarding_selected_ids, ["p1", "p2"])
        self.assertEqual(game_row.onboarding_rating, 5)
        self.assertEqual(game_row.total_rounds, 7)
        self.assertEqual(db.commit_calls, 1)

    async def test_prepare_game_from_persona_rejects_missing_game(self):
        profile = SimpleNamespace(
            onboarding_selected_ids=["p1"],
            model_state={"match_streak_target": 5},
            onboarding_rating=5,
            persona_id="persona-1",
            persona_name="Persona One",
        )

        with self.assertRaises(ValueError) as exc:
            await self.service.prepare_game_from_persona(
                db=_FakeDB([profile, None]),
                game_id="missing-game",
                persona_id="persona-1",
            )

        self.assertEqual(str(exc.exception), "Game not found")

    async def test_get_run_detail_falls_back_to_bundled_persona_when_snapshot_missing(self):
        row = SimpleNamespace(
            id="run-1",
            persona_id="action-thriller-mainstream",
            persona_name="Action Thriller Mainstream",
            category="movies",
            status="completed",
            game_id="game-1",
            created_at=datetime(2026, 1, 1, 12, 0, 0),
            updated_at=datetime(2026, 1, 1, 12, 5, 0),
            started_at=datetime(2026, 1, 1, 12, 1, 0),
            completed_at=datetime(2026, 1, 1, 12, 5, 0),
            metrics={"latest_message": "Done", "game_status": {"status": "ready"}, "final_summary": {"rounds_played": 3}},
            error_message=None,
            config={"max_rounds": 10},
            persona_snapshot={},
            events=[{"type": "status", "title": "Started", "detail": "", "timestamp": datetime(2026, 1, 1, 12, 0, 0)}],
        )
        db = _FakeDB([row])

        with patch.object(self.service, "_active_profile", AsyncMock(return_value=object())):
            detail = await self.service.get_run_detail(db, "run-1")

        self.assertEqual(detail["persona"].id, "action-thriller-mainstream")
        self.assertEqual(detail["config"], {"max_rounds": 10})
        self.assertEqual(detail["game_status"], {"status": "ready"})
        self.assertEqual(detail["final_summary"], {"rounds_played": 3})
        self.assertTrue(detail["has_active_profile"])

    async def test_get_run_detail_rejects_missing_run(self):
        with self.assertRaises(ValueError) as exc:
            await self.service.get_run_detail(_FakeDB([None]), "missing-run")

        self.assertEqual(str(exc.exception), "Persona simulation run not found")


if __name__ == "__main__":
    unittest.main()
