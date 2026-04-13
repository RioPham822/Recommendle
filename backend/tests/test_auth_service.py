import unittest
from datetime import datetime, timedelta

from app.services.auth import AuthService, generate_token, hash_password, verify_password


class _FakeDB:
    def __init__(self, scalar_results):
        self.scalar_results = list(scalar_results)
        self.added = []
        self.commits = 0
        self.refreshed = []

    async def scalar(self, _stmt):
        if self.scalar_results:
            return self.scalar_results.pop(0)
        return None

    def add(self, value):
        self.added.append(value)

    async def commit(self):
        self.commits += 1

    async def refresh(self, value):
        self.refreshed.append(value)


class _User:
    def __init__(
        self,
        user_id="user-1",
        username="alice",
        password_hash_value=None,
        display_name="Alice",
        session_tokens=None,
        created_at=None,
    ):
        self.id = user_id
        self.username = username
        self.password_hash = password_hash_value or hash_password("secret123")
        self.display_name = display_name
        self.role = "user"
        self.games = []
        self.session_tokens = list(session_tokens or [])
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = self.created_at


class AuthServiceTests(unittest.IsolatedAsyncioTestCase):
    def test_password_hash_round_trip_and_bad_hash(self):
        hashed = hash_password("secret123")

        self.assertTrue(verify_password("secret123", hashed))
        self.assertFalse(verify_password("wrong", hashed))
        self.assertFalse(verify_password("secret123", "not-a-valid-hash"))

    def test_generate_token_returns_nonempty_unique_values(self):
        token_a = generate_token()
        token_b = generate_token()

        self.assertTrue(token_a)
        self.assertNotEqual(token_a, token_b)

    async def test_register_user_normalizes_username_and_persists_user(self):
        db = _FakeDB([None])

        result = await AuthService.register_user(db, "  Alice  ", "secret123", "Alice A.")

        self.assertEqual(result["username"], "alice")
        self.assertEqual(result["display_name"], "Alice A.")
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].username, "alice")
        self.assertNotEqual(db.added[0].password_hash, "secret123")
        self.assertEqual(db.commits, 1)
        self.assertEqual(db.refreshed, db.added)

    async def test_register_user_rejects_short_username(self):
        db = _FakeDB([])

        with self.assertRaisesRegex(ValueError, "at least 3 characters"):
            await AuthService.register_user(db, "ab", "secret123")

    async def test_login_user_appends_session_token(self):
        user = _User()
        db = _FakeDB([user])

        result = await AuthService.login_user(db, " Alice ", "secret123")

        self.assertEqual(result["user_id"], "user-1")
        self.assertEqual(result["username"], "alice")
        self.assertEqual(len(user.session_tokens), 1)
        self.assertEqual(user.session_tokens[0]["token"], result["session_token"])
        self.assertEqual(db.commits, 1)

    async def test_verify_token_respects_expiry(self):
        now = datetime.utcnow()
        user = _User(
            session_tokens=[
                {"token": "expired", "expires_at": (now - timedelta(minutes=1)).isoformat()},
                {"token": "valid", "expires_at": (now + timedelta(minutes=1)).isoformat()},
            ]
        )

        self.assertFalse(await AuthService.verify_token(_FakeDB([user]), "user-1", "expired"))
        self.assertTrue(await AuthService.verify_token(_FakeDB([user]), "user-1", "valid"))
        self.assertFalse(await AuthService.verify_token(_FakeDB([None]), "user-1", "valid"))

    async def test_logout_user_removes_matching_token(self):
        user = _User(session_tokens=[{"token": "keep"}, {"token": "drop"}])
        db = _FakeDB([user])

        result = await AuthService.logout_user(db, "user-1", "drop")

        self.assertTrue(result)
        self.assertEqual(user.session_tokens, [{"token": "keep"}])
        self.assertEqual(db.commits, 1)

    async def test_change_password_rejects_incorrect_current_password(self):
        user = _User()
        db = _FakeDB([user])

        with self.assertRaisesRegex(ValueError, "incorrect"):
            await AuthService.change_password(db, "user-1", "wrong", "newsecret")

    async def test_change_password_updates_hash(self):
        user = _User()
        old_hash = user.password_hash
        db = _FakeDB([user])

        result = await AuthService.change_password(db, "user-1", "secret123", "newsecret")

        self.assertTrue(result)
        self.assertNotEqual(user.password_hash, old_hash)
        self.assertTrue(verify_password("newsecret", user.password_hash))
        self.assertEqual(db.commits, 1)


if __name__ == "__main__":
    unittest.main()
