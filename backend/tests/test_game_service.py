import unittest

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


if __name__ == "__main__":
    unittest.main()

