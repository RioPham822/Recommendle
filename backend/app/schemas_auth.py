"""
Pydantic schemas for authentication endpoints.
"""

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class UserRegister(BaseModel):
    """User registration request."""

    username: str = Field(..., min_length=3, max_length=80, description="Unique username")
    password: str = Field(..., min_length=6, max_length=200, description="Password")
    display_name: Optional[str] = Field(None, max_length=100, description="Display name for leaderboards")


class UserLogin(BaseModel):
    """User login request."""

    username: str = Field(..., min_length=3, max_length=80)
    password: str = Field(..., min_length=6, max_length=200)


class UserOut(BaseModel):
    """User response (without sensitive data)."""

    id: str
    username: str
    display_name: str
    created_at: datetime


class AuthTokenOut(BaseModel):
    """Authentication token response."""

    user_id: str
    username: str
    display_name: str
    session_token: str
    expires_at: str


class ChangePasswordRequest(BaseModel):
    """Change password request."""

    old_password: str = Field(..., min_length=6, max_length=200)
    new_password: str = Field(..., min_length=6, max_length=200)


class ChangePasswordResponse(BaseModel):
    """Change password response."""

    success: bool
    message: str
