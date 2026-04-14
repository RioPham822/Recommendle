import unittest
from datetime import datetime

from app.db import GameRecord, ProductRecord, UserRecord, new_id, record_to_dict, utcnow


class DbHelpersTests(unittest.TestCase):
    def test_utcnow_returns_naive_datetime(self):
        stamp = utcnow()

        self.assertIsInstance(stamp, datetime)
        self.assertIsNone(stamp.tzinfo)

    def test_new_id_returns_hex_string(self):
        value = new_id()

        self.assertEqual(len(value), 32)
        int(value, 16)

    def test_record_to_dict_for_product_record_merges_payload(self):
        created_at = datetime.utcnow()
        record = ProductRecord(id="prod-1", category="movies", data={"title": "Interstellar"}, created_at=created_at)

        payload = record_to_dict(record)

        self.assertEqual(
            payload,
            {
                "_id": "prod-1",
                "category": "movies",
                "title": "Interstellar",
                "created_at": created_at,
            },
        )

    def test_record_to_dict_for_non_product_record_renames_id(self):
        created_at = datetime.utcnow()
        record = UserRecord(
            id="user-1",
            username="alice",
            password_hash="hashed",
            display_name="Alice",
            games=["game-1"],
            session_tokens=[],
            created_at=created_at,
            updated_at=created_at,
        )

        payload = record_to_dict(record)

        self.assertEqual(payload["_id"], "user-1")
        self.assertEqual(payload["username"], "alice")
        self.assertEqual(payload["games"], ["game-1"])

    def test_record_to_dict_for_game_record_preserves_fields(self):
        created_at = datetime.utcnow()
        record = GameRecord(
            id="game-1",
            player_name="Alice",
            category="movies",
            status="complete",
            current_round=5,
            total_rounds=5,
            human_score=3,
            ai_score=2,
            model_state={"seen": 1},
            onboarding_pool_ids=["p1"],
            onboarding_selected_ids=["p1"],
            onboarding_rating=4,
            created_at=created_at,
            updated_at=created_at,
        )

        payload = record_to_dict(record)

        self.assertEqual(payload["_id"], "game-1")
        self.assertEqual(payload["category"], "movies")
        self.assertEqual(payload["status"], "complete")
        self.assertEqual(payload["model_state"], {"seen": 1})


if __name__ == "__main__":
    unittest.main()
