import unittest
from datetime import datetime
from unittest.mock import AsyncMock, patch

from fastapi import HTTPException

from app.routes import auth
from app.routes.auth import change_password, get_user, login, logout, register
from app.schemas_auth import ChangePasswordRequest, UserLogin, UserRegister


class AuthRouteTests(unittest.IsolatedAsyncioTestCase):
    async def test_register_returns_auth_token_after_auto_login(self):
        payload = UserRegister(username="alice", password="secret123", display_name="Alice")
        register_result = {"_id": "u1", "username": "alice", "display_name": "Alice"}
        login_result = {
            "user_id": "u1",
            "username": "alice",
            "role": "player",
            "display_name": "Alice",
            "session_token": "token-1",
            "expires_at": "2026-05-01T00:00:00",
        }

        with patch.object(auth.auth_service, "register_user", AsyncMock(return_value=register_result)) as reg_mock, patch.object(
            auth.auth_service,
            "login_user",
            AsyncMock(return_value=login_result),
        ) as login_mock:
            result = await register(payload, db=object())

        reg_mock.assert_awaited_once()
        login_mock.assert_awaited_once()
        self.assertEqual(result.user_id, "u1")
        self.assertEqual(result.session_token, "token-1")

    async def test_register_translates_validation_error_to_http_400(self):
        payload = UserRegister(username="alice", password="secret123", display_name="Alice")
        with patch.object(auth.auth_service, "register_user", AsyncMock(side_effect=ValueError("duplicate"))):
            with self.assertRaises(HTTPException) as exc:
                await register(payload, db=object())

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "duplicate")

    async def test_login_returns_auth_token(self):
        payload = UserLogin(username="alice", password="secret123")
        login_result = {
            "user_id": "u1",
            "username": "alice",
            "role": "player",
            "display_name": "Alice",
            "session_token": "token-1",
            "expires_at": "2026-05-01T00:00:00",
        }

        with patch.object(auth.auth_service, "login_user", AsyncMock(return_value=login_result)) as mocked:
            result = await login(payload, db=object())

        mocked.assert_awaited_once()
        self.assertEqual(result.username, "alice")

    async def test_login_translates_value_error_to_http_401(self):
        payload = UserLogin(username="alice", password="secret123")
        with patch.object(auth.auth_service, "login_user", AsyncMock(side_effect=ValueError("bad creds"))):
            with self.assertRaises(HTTPException) as exc:
                await login(payload, db=object())

        self.assertEqual(exc.exception.status_code, 401)
        self.assertEqual(exc.exception.detail, "bad creds")

    async def test_get_user_returns_public_fields(self):
        user = {
            "_id": "u1",
            "username": "alice",
            "role": "admin",
            "display_name": "Alice",
            "created_at": datetime(2026, 1, 1, 12, 0, 0),
        }
        with patch.object(auth.auth_service, "get_user", AsyncMock(return_value=user)) as mocked:
            result = await get_user("u1", db=object())

        mocked.assert_awaited_once()
        self.assertEqual(result.id, "u1")
        self.assertEqual(result.role, "admin")

    async def test_get_user_raises_404_when_missing(self):
        with patch.object(auth.auth_service, "get_user", AsyncMock(return_value=None)):
            with self.assertRaises(HTTPException) as exc:
                await get_user("missing", db=object())

        self.assertEqual(exc.exception.status_code, 404)
        self.assertEqual(exc.exception.detail, "User not found")

    async def test_change_password_returns_success_response(self):
        payload = ChangePasswordRequest(old_password="secret123", new_password="newsecret")
        with patch.object(auth.auth_service, "change_password", AsyncMock(return_value=True)) as mocked:
            result = await change_password(payload, user_id="u1", db=object())

        mocked.assert_awaited_once()
        self.assertTrue(result.success)
        self.assertIn("successfully", result.message)

    async def test_change_password_handles_false_and_value_error(self):
        payload = ChangePasswordRequest(old_password="secret123", new_password="newsecret")
        with patch.object(auth.auth_service, "change_password", AsyncMock(return_value=False)):
            with self.assertRaises(HTTPException) as failed:
                await change_password(payload, user_id="u1", db=object())
        self.assertEqual(failed.exception.status_code, 400)

        with patch.object(auth.auth_service, "change_password", AsyncMock(side_effect=ValueError("too weak"))):
            with self.assertRaises(HTTPException) as exc:
                await change_password(payload, user_id="u1", db=object())
        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "too weak")

    async def test_logout_returns_success_message(self):
        with patch.object(auth.auth_service, "logout_user", AsyncMock(return_value=True)) as mocked:
            result = await logout(user_id="u1", session_token="token-1", db=object())

        mocked.assert_awaited_once()
        self.assertEqual(result, {"message": "Logged out successfully"})

    async def test_logout_raises_http_400_on_failure(self):
        with patch.object(auth.auth_service, "logout_user", AsyncMock(return_value=False)):
            with self.assertRaises(HTTPException) as exc:
                await logout(user_id="u1", session_token="token-1", db=object())

        self.assertEqual(exc.exception.status_code, 400)
        self.assertEqual(exc.exception.detail, "Failed to logout")


if __name__ == "__main__":
    unittest.main()
