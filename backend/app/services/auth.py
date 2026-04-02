"""
User authentication service for multi-user support.
Handles user registration, login, and session management.
"""

import hashlib
import logging
import secrets
from datetime import datetime, timedelta
from typing import Optional

from fastapi import Depends, Header, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import UserRecord, get_db, new_id, settings

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


def active_session_tokens(tokens: list[dict] | None) -> list[dict]:
    """Return only unexpired session token entries."""
    now = datetime.utcnow()
    active: list[dict] = []
    for token in tokens or []:
        expires_at = token.get("expires_at")
        if not expires_at:
            continue
        try:
            if datetime.fromisoformat(str(expires_at)) > now:
                active.append(token)
        except ValueError:
            continue
    return active


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

        admin_count = await db.scalar(select(func.count()).select_from(UserRecord).where(UserRecord.role == "admin"))
        role = "admin" if not admin_count else "player"

        user = UserRecord(
            id=new_id(),
            username=username,
            role=role,
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
            "role": user.role,
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
            "role": user.role,
            "display_name": user.display_name,
            "session_token": token,
            "expires_at": expiry.isoformat(),
        }

    @staticmethod
    async def verify_token(
        db: AsyncSession,
        user_id: str,
        token: str,
    ) -> Optional[UserRecord]:
        """Return user record when a token exists and is not expired."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return None
        valid_tokens = active_session_tokens(user.session_tokens)
        if len(valid_tokens) != len(user.session_tokens or []):
            user.session_tokens = valid_tokens
            user.updated_at = datetime.utcnow()
            await db.commit()
        for session_token in valid_tokens:
            if session_token.get("token") != token:
                continue
            return user
        return None

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
            "role": user.role,
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

    @staticmethod
    async def list_users(db: AsyncSession) -> list[dict]:
        """Return all users for admin management."""
        rows = (await db.execute(select(UserRecord).order_by(UserRecord.created_at.desc()))).scalars().all()
        changed = False
        for user in rows:
            valid_tokens = active_session_tokens(user.session_tokens)
            if len(valid_tokens) != len(user.session_tokens or []):
                user.session_tokens = valid_tokens
                user.updated_at = datetime.utcnow()
                changed = True
        if changed:
            await db.commit()
        return [
            {
                "_id": user.id,
                "username": user.username,
                "role": user.role,
                "display_name": user.display_name,
                "created_at": user.created_at,
                "updated_at": user.updated_at,
                "active_sessions": len(user.session_tokens or []),
            }
            for user in rows
        ]

    @staticmethod
    async def update_user_role(db: AsyncSession, user_id: str, role: str) -> dict:
        """Promote/demote a user between supported roles."""
        normalized_role = role.strip().lower()
        if normalized_role not in {"player", "admin"}:
            raise ValueError("Role must be either 'player' or 'admin'")
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            raise ValueError("User not found")
        user.role = normalized_role
        user.updated_at = datetime.utcnow()
        await db.commit()
        return {
            "_id": user.id,
            "username": user.username,
            "role": user.role,
            "display_name": user.display_name,
            "created_at": user.created_at,
            "updated_at": user.updated_at,
        }

    @staticmethod
    async def revoke_user_sessions(db: AsyncSession, user_id: str) -> bool:
        """Invalidate all active sessions for one user."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            return False
        user.session_tokens = []
        user.updated_at = datetime.utcnow()
        await db.commit()
        return True

    @staticmethod
    async def clear_user_sessions(db: AsyncSession, user_id: str) -> int:
        """Invalidate all currently active sessions for one user and return the count removed."""
        user = await db.scalar(select(UserRecord).where(UserRecord.id == user_id))
        if not user:
            raise ValueError("User not found")
        valid_tokens = active_session_tokens(user.session_tokens)
        removed_count = len(valid_tokens)
        user.session_tokens = []
        user.updated_at = datetime.utcnow()
        await db.commit()
        return removed_count

    @staticmethod
    async def ensure_bootstrap_admin(db: AsyncSession) -> None:
        """Create a configured admin account on startup when requested."""
        username = settings.admin_username.strip().lower()
        password = settings.admin_password
        if not username or not password:
            return
        existing = await db.scalar(select(UserRecord).where(UserRecord.username == username))
        if existing:
            if existing.role != "admin":
                existing.role = "admin"
                existing.updated_at = datetime.utcnow()
                await db.commit()
            return
        user = UserRecord(
            id=new_id(),
            username=username,
            role="admin",
            password_hash=hash_password(password),
            display_name=settings.admin_display_name.strip() or "Administrator",
            games=[],
            session_tokens=[],
            created_at=datetime.utcnow(),
            updated_at=datetime.utcnow(),
        )
        db.add(user)
        await db.commit()
        logger.info("Bootstrap admin account created for %s", username)


async def get_current_user(
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None),
) -> UserRecord:
    """Resolve the authenticated user from request headers."""
    if not x_user_id or not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(status_code=401, detail="Authentication required")
    token = authorization.split(" ", 1)[1].strip()
    user = await auth_service.verify_token(db, x_user_id, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


async def get_optional_current_user(
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None),
) -> UserRecord | None:
    """Resolve the authenticated user when auth headers are present, otherwise return None."""
    if not x_user_id or not authorization:
        return None
    if not authorization.lower().startswith("bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    user = await auth_service.verify_token(db, x_user_id, token)
    if not user:
        raise HTTPException(status_code=401, detail="Invalid or expired session")
    return user


async def require_admin(
    db: AsyncSession = Depends(get_db),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
    authorization: str | None = Header(default=None),
) -> UserRecord:
    """Resolve the authenticated admin user from request headers."""
    user = await get_current_user(db, x_user_id=x_user_id, authorization=authorization)
    if user.role != "admin":
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


auth_service = AuthService()
