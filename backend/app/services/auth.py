"""
User authentication service for multi-user support.
Handles user registration, login, and session management.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import UserRecord, new_id

logger = logging.getLogger(__name__)

TOKEN_EXPIRY_DAYS = 7


def hash_password(password: str) -> str:
    """Hash a plain password with per-password salt using PBKDF2-SHA256."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Validate a plain password against stored `salt$hash` format."""
    try:
        salt, pwd_hash = hashed.split("$")
        computed_hash = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), 100000)
        return computed_hash.hex() == pwd_hash
    except Exception as exc:
        logger.error(f"Error verifying password: {exc}")
        return False


def generate_token() -> str:
    """Generate a URL-safe session token."""
    return secrets.token_urlsafe(32)


class AuthService:
    """User registration/login/session management service."""

    @staticmethod
    async def register_user(
        db: AsyncSession,
        username: str,
        password: str,
        display_name: Optional[str] = None,
    ) -> dict:
        """Create a new user account."""
        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters")

        username = username.strip().lower()
        existing_user = await db.scalar(select(UserRecord).where(UserRecord.username == username))
        if existing_user:
            raise ValueError("Username already exists")

        user = UserRecord(
            id=new_id(),
            username=username,
            password_hash=hash_password(password),
            display_name=display_name or username,
            games=[],
            session_tokens=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        logger.info(f"User registered: {username}")
        return {
            "_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "created_at": user.created_at,
            "session_tokens": user.session_tokens,
        }

    @staticmethod
    async def login_user(
        db: AsyncSession,
        username: str,
        password: str,
    ) -> dict:
        """Authenticate user and issue a new expiring session token."""
        username = username.strip().lower()
        user = await db.scalar(select(UserRecord).where(UserRecord.username == username))
        if not user or not verify_password(password, user.password_hash):
            raise ValueError("Invalid username or password")

        token = generate_token()
        expiry = datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
        tokens = list(user.session_tokens or [])
        tokens.append(
            {
                "token": token,
                "created_at": datetime.utcnow().isoformat(),
                "expires_at": expiry.isoformat(),
                "ip_address": None,
            }
        )
        user.session_tokens = tokens
        user.updated_at = datetime.utcnow()
        await db.commit()

        logger.info(f"User logged in: {username}")
        return {
            "user_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "session_token": token,
            "expires_at": expiry.isoformat(),
        }

    @staticmethod
    async def verify_token(
        db: AsyncSession,
        user_id: str,
        token: str,
    ) -> bool:
        """Return True when a user token exists and is not expired."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return False
        now = datetime.utcnow()
        for session_token in user.session_tokens or []:
            if session_token.get("token") != token:
                continue
            expires_at = session_token.get("expires_at")
            if not expires_at:
                continue
            try:
                if datetime.fromisoformat(str(expires_at)) > now:
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    async def logout_user(
        db: AsyncSession,
        user_id: str,
        token: str,
    ) -> bool:
        """Invalidate a single session token for a user."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return False
        before = len(user.session_tokens or [])
        user.session_tokens = [t for t in (user.session_tokens or []) if t.get("token") != token]
        user.updated_at = datetime.utcnow()
        await db.commit()
        return len(user.session_tokens or []) < before

    @staticmethod
    async def get_user(
        db: AsyncSession,
        user_id: str,
    ) -> Optional[dict]:
        """Fetch public user profile fields by ID."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return None
        return {
            "_id": user.id,
            "username": user.username,
            "display_name": user.display_name,
            "created_at": user.created_at,
        }

    @staticmethod
    async def change_password(
        db: AsyncSession,
        user_id: str,
        old_password: str,
        new_password: str,
    ) -> bool:
        """Update a user's password after verifying current credentials."""
        if not new_password or len(new_password) < 6:
            raise ValueError("New password must be at least 6 characters")

        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return False
        if not verify_password(old_password, user.password_hash):
            raise ValueError("Current password is incorrect")

        user.password_hash = hash_password(new_password)
        user.updated_at = datetime.utcnow()
        await db.commit()
        logger.info(f"Password changed for user: {user.username}")
        return True


auth_service = AuthService()
