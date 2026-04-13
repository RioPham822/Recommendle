import unittest
from datetime import datetime
from types import SimpleNamespace

from app.services.game_service import GameService


class _FakeFeatureSpace:
    def __init__(self):
        self.feature_index = {
            "Cat::Fountain_Pens::Cat::Product_Type::Fountain Pens": 0,
            "Cat::Fountain_Pens::Multi::Tags::Products": 1,
            "Cat::Fountain_Pens::Multi::Option::Nib Size|Medium": 2,
            "cat::fountain_pens::num::price_min_z": 3,
        }

    def vectorize(self, _product):
        return [1.0, 1.0, 1.0, 1.0]


class GameServiceTests(unittest.TestCase):
    def test_product_card_flattens_pen_options_for_display(self):
        service = GameService()
        product = {
            "_id": "pen-1",
            "category": "fountain_pens",
            "title": "Pilot Custom 823",
            "vendor": "Pilot",
            "product_type": "Fountain Pen",
            "options": {
                "Nib Size": ["Extra-Fine", "Fine", "Medium"],
            },
            "price_min": 288.0,
            "price_max": 336.0,
            "tags": ["gold nib"],
            "images": [{"url": "https://example.com/pen.jpg"}],
        }

        card = service._product_card(product)

        self.assertNotIn("options", card["attributes"])
        self.assertEqual(card["attributes"]["Nib Size"], ["Extra-Fine", "Fine", "Medium"])
        self.assertEqual(card["attributes"]["product_type"], "Fountain Pen")

    def test_predicted_match_features_hide_raw_model_tokens(self):
        service = GameService()
        service.recommender.feature_space = _FakeFeatureSpace()
        state = {
            "user_vec": [0.9, 0.8, 0.7, 0.6],
        }

        labels = service._predicted_match_features(state, {"_id": "candidate-1"})

        self.assertIn("Medium Nib Size", labels)
        self.assertIn("Higher Price Range", labels)
        self.assertFalse(any("::" in label for label in labels))
        self.assertFalse(any(label.lower() in {"pens", "products"} for label in labels))

    def test_reset_run_progress_keeps_preferences_but_clears_run_counters(self):
        state = {
            "user_vec": [0.9, 0.4],
            "active_preference_ids": ["a", "b"],
            "seed_preferences": {"likes": {"vendor": ["Pelikan"]}},
            "current_match_streak": 4,
            "longest_match_streak": 5,
            "rounds_played": 11,
            "total_matches": 7,
        }

        reset = GameService._reset_run_progress(state)

        self.assertEqual(reset["user_vec"], [0.9, 0.4])
        self.assertEqual(reset["active_preference_ids"], ["a", "b"])
        self.assertEqual(reset["seed_preferences"], {"likes": {"vendor": ["Pelikan"]}})
        self.assertEqual(reset["current_match_streak"], 0)
        self.assertEqual(reset["longest_match_streak"], 0)
        self.assertEqual(reset["rounds_played"], 0)
        self.assertEqual(reset["total_matches"], 0)

    def test_has_carryable_profile_requires_model_state_and_completed_onboarding(self):
        carryable = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [str(index) for index in range(10)],
        }
        minimal_completed = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": ["1", "2"],
        }
        missing_picks = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [],
        }
        too_many_picks = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [str(index) for index in range(11)],
        }

        self.assertTrue(GameService._has_carryable_profile(carryable))
        self.assertTrue(GameService._has_carryable_profile(minimal_completed))
        self.assertFalse(GameService._has_carryable_profile(missing_picks))
        self.assertFalse(GameService._has_carryable_profile(too_many_picks))
        self.assertFalse(GameService._has_carryable_profile({"onboarding_selected_ids": [str(index) for index in range(10)]}))


class OnboardingRefreshTests(unittest.IsolatedAsyncioTestCase):
    async def test_build_onboarding_pool_refresh_preserves_selected_ids(self):
        service = GameService()
        products = [{"_id": f"p{index}"} for index in range(250)]
        original_pool = [f"p{index}" for index in range(100)]

        async def fake_all_products(_db, _category):
            return products

        service._all_products_for_onboarding_sample = fake_all_products
        service._diverse_onboarding_sample = lambda all_products, _game_id, _category: [str(p["_id"]) for p in all_products[:100]]

        refreshed = await service._build_onboarding_pool(
            None,
            {
                "_id": "game-1",
                "mode": "classic",
                "onboarding_pool_ids": original_pool,
            },
            "fountain_pens",
            preserved_ids=["p2", "p7", "p15"],
            force_refresh=True,
        )

        self.assertEqual(refreshed[:3], ["p2", "p7", "p15"])
        self.assertEqual(len(refreshed), 100)
        self.assertTrue(set(["p2", "p7", "p15"]).issubset(set(refreshed)))
        self.assertNotIn("p0", refreshed)
        self.assertNotIn("p99", refreshed)
        self.assertIn("p100", refreshed)
        self.assertIn("p196", refreshed)


class _ResumeFakeDB:
    def __init__(self, scalar_results=None):
        self.scalar_results = list(scalar_results or [])

    async def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None


class GameServiceHelperTests(unittest.TestCase):
    def test_normalize_mode_defaults_to_classic(self):
        self.assertEqual(GameService._normalize_mode(None), "classic")

    def test_normalize_mode_accepts_classic_and_beta(self):
        self.assertEqual(GameService._normalize_mode("classic"), "classic")
        self.assertEqual(GameService._normalize_mode(" beta "), "beta")

    def test_normalize_mode_rejects_invalid_mode(self):
        with self.assertRaisesRegex(ValueError, "Unsupported game mode"):
            GameService._normalize_mode("arcade")

    def test_rng_for_is_deterministic_for_same_inputs(self):
        rng_a = GameService._rng_for("game-1", 2, "salt")
        rng_b = GameService._rng_for("game-1", 2, "salt")
        rng_c = GameService._rng_for("game-1", 3, "salt")

        seq_a = [rng_a.random() for _ in range(5)]
        seq_b = [rng_b.random() for _ in range(5)]
        seq_c = [rng_c.random() for _ in range(5)]

        self.assertEqual(seq_a, seq_b)
        self.assertNotEqual(seq_a, seq_c)

    def test_game_category_falls_back_to_fountain_pens_on_invalid_value(self):
        self.assertEqual(GameService._game_category({"category": "movies"}), "movies")
        self.assertEqual(GameService._game_category({"category": "bad-category"}), "fountain_pens")
        self.assertEqual(GameService._game_category({}), "fountain_pens")

    def test_filter_visible_products_keeps_all_non_movie_products(self):
        products = [
            {"_id": "p1", "category": "fountain_pens"},
            {"_id": "p2", "category": "fountain_pens"},
        ]

        result = GameService._filter_visible_products(products, "fountain_pens")

        self.assertEqual(result, products)

    def test_filter_visible_products_filters_low_vote_movies(self):
        products = [
            {"_id": "m1", "vote_count": 999},
            {"_id": "m2", "vote_count": 1000},
            {"_id": "m3", "vote_count": 2500},
            {"_id": "m4", "vote_count": "bad"},
        ]

        result = GameService._filter_visible_products(products, "movies")

        self.assertEqual([product["_id"] for product in result], ["m2", "m3"])

    def test_is_redesigned_game_checks_schema_version(self):
        self.assertTrue(GameService._is_redesigned_game({"schema_version": 3}))
        self.assertTrue(GameService._is_redesigned_game({"schema_version": 4}))
        self.assertFalse(GameService._is_redesigned_game({"schema_version": 2}))
        self.assertFalse(GameService._is_redesigned_game(None))

    def test_empty_seed_preferences_shape(self):
        result = GameService._empty_seed_preferences()

        self.assertEqual(
            result,
            {
                "likes": {},
                "dislikes": {},
                "like_product_ids": [],
                "dislike_product_ids": [],
            },
        )

    def test_ensure_redesign_state_adds_defaults(self):
        result = GameService._ensure_redesign_state({"user_vec": [0.1, 0.2]})

        self.assertEqual(result["user_vec"], [0.1, 0.2])
        self.assertEqual(result["match_streak_target"], GameService.DEFAULT_MATCH_STREAK_TARGET)
        self.assertEqual(result["current_match_streak"], 0)
        self.assertEqual(result["longest_match_streak"], 0)
        self.assertEqual(result["rounds_played"], 0)
        self.assertEqual(result["total_matches"], 0)
        self.assertEqual(result["active_preference_ids"], [])
        self.assertIn("seed_preferences", result)

    def test_rounds_played_uses_model_state_for_redesigned_game(self):
        redesigned = {
            "schema_version": 3,
            "current_round": 1,
            "model_state": {"rounds_played": 4},
        }
        legacy = {
            "schema_version": 2,
            "current_round": 3,
            "model_state": {"rounds_played": 9},
        }

        self.assertEqual(GameService._rounds_played(redesigned), 4)
        self.assertEqual(GameService._rounds_played(legacy), 3)

    def test_match_progress_reads_state_or_defaults(self):
        game = {
            "model_state": {
                "current_match_streak": 2,
                "longest_match_streak": 5,
                "match_streak_target": 7,
            }
        }

        self.assertEqual(GameService._match_progress(game), (2, 5, 7))
        self.assertEqual(
            GameService._match_progress({"model_state": {}}),
            (0, 0, GameService.DEFAULT_MATCH_STREAK_TARGET),
        )

    def test_align_state_to_feature_space_pads_truncates_and_coerces_values(self):
        service = GameService()
        model = SimpleNamespace(
            feature_space=SimpleNamespace(
                feature_index={"a": 0, "b": 1, "c": 2}
            )
        )

        state = {"user_vec": [1, "bad"]}
        changed = service._align_state_to_feature_space(model, state)
        self.assertTrue(changed)
        self.assertEqual(state["user_vec"], [1.0, 0.0, 0.0])

        state = {"user_vec": [1, 2, 3, 4]}
        changed = service._align_state_to_feature_space(model, state)
        self.assertTrue(changed)
        self.assertEqual(state["user_vec"], [1.0, 2.0, 3.0])

        state = {"user_vec": [1, 2, 3]}
        changed = service._align_state_to_feature_space(model, state)
        self.assertFalse(changed)
        self.assertEqual(state["user_vec"], [1.0, 2.0, 3.0])

    def test_round_candidate_target_uses_current_category_profiles(self):
        service = GameService()

        self.assertEqual(service._round_candidate_target("fountain_pens"), 10)
        self.assertEqual(service._round_candidate_target("movies"), 10)

    def test_build_round_duel_candidates_returns_two_ids(self):
        rng = GameService._rng_for("game-1", 1, "duel")
        scored = [
            (4.9, {"_id": "a"}),
            (4.8, {"_id": "b"}),
            (4.7, {"_id": "c"}),
            (4.6, {"_id": "d"}),
        ]

        result = GameService._build_round_duel_candidates(rng, scored)

        self.assertEqual(len(result), 2)
        self.assertEqual(len(set(result)), 2)
        self.assertTrue(set(result).issubset({"a", "b", "c", "d"}))

    def test_build_round_candidates_returns_all_when_scored_list_is_small(self):
        service = GameService()
        scored = [(4.5, {"_id": str(i)}) for i in range(5)]

        result = service._build_round_candidates("game-1", 1, "fountain_pens", scored)

        self.assertEqual(set(result), {str(i) for i in range(5)})
        self.assertEqual(len(result), 5)

    def test_game_out_payload_builds_consistent_response(self):
        service = GameService()
        game = {
            "_id": "game-1",
            "schema_version": 3,
            "player_name": "Sai",
            "category": "fountain_pens",
            "mode": "beta",
            "status": "playing",
            "total_rounds": 5,
            "human_score": 2,
            "ai_score": 1,
            "created_at": datetime(2026, 1, 1),
            "current_round": 2,
            "model_state": {
                "rounds_played": 2,
                "current_match_streak": 1,
                "longest_match_streak": 2,
                "match_streak_target": 5,
            },
        }

        result = service._game_out_payload(game, resumed=True)

        self.assertEqual(result["id"], "game-1")
        self.assertEqual(result["player_name"], "Sai")
        self.assertEqual(result["mode"], "beta")
        self.assertEqual(result["current_match_streak"], 1)
        self.assertEqual(result["longest_match_streak"], 2)
        self.assertEqual(result["rounds_played"], 2)
        self.assertTrue(result["resumed"])


class ResumeStateTests(unittest.IsolatedAsyncioTestCase):
    async def test_get_resume_state_returns_empty_for_blank_name(self):
        service = GameService()
        result = await service.get_resume_state(_ResumeFakeDB(), "   ", category="fountain_pens")

        self.assertFalse(result["exists"])
        self.assertFalse(result["can_start_fresh"])
        self.assertIsNone(result["game_id"])

    async def test_get_resume_state_returns_no_active_game_but_can_start_fresh(self):
        service = GameService()
        db = _ResumeFakeDB(
            scalar_results=[
                SimpleNamespace(id="old-game"),
                None,
            ]
        )

        result = await service.get_resume_state(db, "Sai", category="fountain_pens")

        self.assertFalse(result["exists"])
        self.assertTrue(result["can_start_fresh"])
        self.assertEqual(result["player_name"], "Sai")
        self.assertEqual(result["category"], "fountain_pens")

    async def test_get_resume_state_returns_active_game_details(self):
        service = GameService()
        active_game = SimpleNamespace(
            id="game-7",
            player_name="Sai",
            category="fountain_pens",
            status="playing",
            current_round=3,
            total_rounds=5,
        )
        db = _ResumeFakeDB(
            scalar_results=[
                SimpleNamespace(id="any-game"),
                active_game,
            ]
        )

        result = await service.get_resume_state(db, "Sai", category="fountain_pens")

        self.assertTrue(result["exists"])
        self.assertTrue(result["can_start_fresh"])
        self.assertEqual(result["game_id"], "game-7")
        self.assertEqual(result["status"], "playing")
        self.assertEqual(result["current_round"], 3)
        self.assertEqual(result["total_rounds"], 5)


if __name__ == "__main__":
    unittest.main()
