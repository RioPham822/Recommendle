import unittest

from app.services.game_service import GameService


class OnboardingSelectionBoundsTests(unittest.TestCase):
    def test_carryable_profile_accepts_one_to_ten_onboarding_items(self):
        carryable_min = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": ["1"],
        }
        carryable_max = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [str(index) for index in range(10)],
        }
        incomplete = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [],
        }
        too_many = {
            "model_state": {"user_vec": [0.2, 0.8]},
            "onboarding_selected_ids": [str(index) for index in range(11)],
        }

        self.assertTrue(GameService._has_carryable_profile(carryable_min))
        self.assertTrue(GameService._has_carryable_profile(carryable_max))
        self.assertFalse(GameService._has_carryable_profile(incomplete))
        self.assertFalse(GameService._has_carryable_profile(too_many))


if __name__ == "__main__":
    unittest.main()
