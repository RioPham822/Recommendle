"""
Authentication routes for user registration, login, and account management.
"""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from ..db import get_db
from ..schemas_auth import (
    UserRegister,
    UserLogin,
    AuthTokenOut,
    UserOut,
    ChangePasswordRequest,
    ChangePasswordResponse,
)
from ..services.auth import auth_service

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=AuthTokenOut)
async def register(
    payload: UserRegister,
    db: AsyncSession = Depends(get_db),
):
    """Register a new user and return auth token."""
    try:
        user = await auth_service.register_user(
            db,
            username=payload.username,
            password=payload.password,
            display_name=payload.display_name,
        )
        
        # Auto-login after registration
        auth_result = await auth_service.login_user(
            db,
            username=payload.username,
            password=payload.password,
        )
        
        return AuthTokenOut(**auth_result)
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/login", response_model=AuthTokenOut)
async def login(
    payload: UserLogin,
    db: AsyncSession = Depends(get_db),
):
    """Login user and return auth token."""
    try:
        auth_result = await auth_service.login_user(
            db,
            username=payload.username,
            password=payload.password,
        )
        return AuthTokenOut(**auth_result)
    
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e)) from e


@router.get("/user/{user_id}", response_model=UserOut)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
):
    """Get user information by user ID."""
    user = await auth_service.get_user(db, user_id)
    
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserOut(
        id=user.get("_id"),
        username=user.get("username"),
        display_name=user.get("display_name"),
        created_at=user.get("created_at"),
    )


@router.post("/change-password", response_model=ChangePasswordResponse)
async def change_password(
    payload: ChangePasswordRequest,
    user_id: str,  # Should come from auth header in production
    db: AsyncSession = Depends(get_db),
):
    """Change user password."""
    try:
        success = await auth_service.change_password(
            db,
            user_id=user_id,
            old_password=payload.old_password,
            new_password=payload.new_password,
        )
        
        if not success:
            raise HTTPException(status_code=400, detail="Failed to change password")
        
        return ChangePasswordResponse(
            success=True,
            message="Password changed successfully",
        )
    
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@router.post("/logout")
async def logout(
    user_id: str,
    session_token: str,
    db: AsyncSession = Depends(get_db),
):
    """Logout user by invalidating session token."""
    success = await auth_service.logout_user(db, user_id, session_token)
    
    if not success:
        raise HTTPException(status_code=400, detail="Failed to logout")
    
    return {"message": "Logged out successfully"}
