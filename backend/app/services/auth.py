"""
User authentication service for multi-user support.
Handles user registration, login, and session management.
"""

from datetime import datetime, timedelta
from typing import Optional
from motor.motor_asyncio import AsyncIOMotorDatabase
from bson import ObjectId
import hashlib
import secrets
import logging

logger = logging.getLogger(__name__)

# Session token expiry (7 days)
TOKEN_EXPIRY_DAYS = 7


def hash_password(password: str) -> str:
    """Hash password using SHA256 with salt."""
    salt = secrets.token_hex(16)
    pwd_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
    return f"{salt}${pwd_hash.hex()}"


def verify_password(password: str, hashed: str) -> bool:
    """Verify password against hashed version."""
    try:
        salt, pwd_hash = hashed.split('$')
        computed_hash = hashlib.pbkdf2_hmac('sha256', password.encode('utf-8'), bytes.fromhex(salt), 100000)
        return computed_hash.hex() == pwd_hash
    except Exception as e:
        logger.error(f"Error verifying password: {e}")
        return False


def generate_token() -> str:
    """Generate a secure session token."""
    return secrets.token_urlsafe(32)


class AuthService:
    """Authentication service for user management."""

    @staticmethod
    async def register_user(
        db: AsyncIOMotorDatabase,
        username: str,
        password: str,
        display_name: Optional[str] = None
    ) -> dict:
        """
        Register a new user.
        
        Args:
            db: MongoDB database instance
            username: Unique username
            password: User password (will be hashed)
            display_name: Optional display name for leaderboards
            
        Returns:
            User document with ID
            
        Raises:
            ValueError: If username already exists or invalid input
        """
        
        # Validate input
        if not username or len(username) < 3:
            raise ValueError("Username must be at least 3 characters")
        if not password or len(password) < 6:
            raise ValueError("Password must be at least 6 characters")
        
        username = username.strip().lower()
        
        # Check if user already exists
        existing_user = await db.users.find_one({"username": username})
        if existing_user:
            raise ValueError("Username already exists")
        
        # Create new user
        user_doc = {
            "username": username,
            "password_hash": hash_password(password),
            "display_name": display_name or username,
            "created_at": datetime.utcnow(),
            "updated_at": datetime.utcnow(),
            "games": [],  # List of game IDs
            "session_tokens": [],  # Active session tokens
        }
        
        result = await db.users.insert_one(user_doc)
        user_doc["_id"] = result.inserted_id
        
        logger.info(f"User registered: {username}")
        return user_doc

    @staticmethod
    async def login_user(
        db: AsyncIOMotorDatabase,
        username: str,
        password: str
    ) -> dict:
        """
        Login user and create a session token.
        
        Args:
            db: MongoDB database instance
            username: Username
            password: Password
            
        Returns:
            Dict with user_id and session_token
            
        Raises:
            ValueError: If credentials are invalid
        """
        
        username = username.strip().lower()
        
        # Find user
        user = await db.users.find_one({"username": username})
        if not user:
            raise ValueError("Invalid username or password")
        
        # Verify password
        if not verify_password(password, user["password_hash"]):
            raise ValueError("Invalid username or password")
        
        # Generate session token
        token = generate_token()
        expiry = datetime.utcnow() + timedelta(days=TOKEN_EXPIRY_DAYS)
        
        # Store token in user document
        session_record = {
            "token": token,
            "created_at": datetime.utcnow(),
            "expires_at": expiry,
            "ip_address": None,  # Can be captured from request
        }
        
        await db.users.update_one(
            {"_id": user["_id"]},
            {"$push": {"session_tokens": session_record}}
        )
        
        logger.info(f"User logged in: {username}")
        
        return {
            "user_id": str(user["_id"]),
            "username": user["username"],
            "display_name": user.get("display_name", username),
            "session_token": token,
            "expires_at": expiry.isoformat(),
        }

    @staticmethod
    async def verify_token(
        db: AsyncIOMotorDatabase,
        user_id: str,
        token: str
    ) -> bool:
        """
        Verify a session token is valid.
        
        Args:
            db: MongoDB database instance
            user_id: User ID
            token: Session token
            
        Returns:
            True if token is valid, False otherwise
        """
        
        try:
            # Validate user_id
            if not ObjectId.is_valid(user_id):
                return False
            
            user = await db.users.find_one(
                {
                    "_id": ObjectId(user_id),
                    "session_tokens.token": token,
                    "session_tokens.expires_at": {"$gt": datetime.utcnow()},
                }
            )
            
            return user is not None
        
        except Exception as e:
            logger.error(f"Error verifying token: {e}")
            return False

    @staticmethod
    async def logout_user(
        db: AsyncIOMotorDatabase,
        user_id: str,
        token: str
    ) -> bool:
        """
        Logout user by invalidating their session token.
        
        Args:
            db: MongoDB database instance
            user_id: User ID
            token: Session token
            
        Returns:
            True if logout successful
        """
        
        try:
            if not ObjectId.is_valid(user_id):
                return False
            
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {"$pull": {"session_tokens": {"token": token}}}
            )
            
            return result.modified_count > 0
        
        except Exception as e:
            logger.error(f"Error logging out: {e}")
            return False

    @staticmethod
    async def get_user(
        db: AsyncIOMotorDatabase,
        user_id: str
    ) -> Optional[dict]:
        """
        Get user information (without sensitive data).
        
        Args:
            db: MongoDB database instance
            user_id: User ID
            
        Returns:
            User document (without password_hash), or None if not found
        """
        
        try:
            if not ObjectId.is_valid(user_id):
                return None
            
            user = await db.users.find_one(
                {"_id": ObjectId(user_id)},
                {"password_hash": 0, "session_tokens": 0}
            )
            
            if user:
                user["_id"] = str(user["_id"])
            
            return user
        
        except Exception as e:
            logger.error(f"Error getting user: {e}")
            return None

    @staticmethod
    async def change_password(
        db: AsyncIOMotorDatabase,
        user_id: str,
        old_password: str,
        new_password: str
    ) -> bool:
        """
        Change user password.
        
        Args:
            db: MongoDB database instance
            user_id: User ID
            old_password: Current password for verification
            new_password: New password
            
        Returns:
            True if password changed successfully
        """
        
        try:
            if not ObjectId.is_valid(user_id):
                return False
            
            if not new_password or len(new_password) < 6:
                raise ValueError("New password must be at least 6 characters")
            
            user = await db.users.find_one({"_id": ObjectId(user_id)})
            if not user:
                return False
            
            # Verify old password
            if not verify_password(old_password, user["password_hash"]):
                raise ValueError("Current password is incorrect")
            
            # Update password
            result = await db.users.update_one(
                {"_id": ObjectId(user_id)},
                {
                    "$set": {
                        "password_hash": hash_password(new_password),
                        "updated_at": datetime.utcnow()
                    }
                }
            )
            
            logger.info(f"Password changed for user: {user.get('username')}")
            return result.modified_count > 0
        
        except Exception as e:
            logger.error(f"Error changing password: {e}")
            return False


# Global service instance
auth_service = AuthService()
