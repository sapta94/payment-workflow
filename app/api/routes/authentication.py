from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select,update
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone

from app.core.security import create_access_token, get_current_user_id
from app.database.base import get_db
from app.database.models import User, UserSession
from app.utils.utils import hash_password, verify_password

router = APIRouter()


class RegisterUserRequest(BaseModel):
    """Body required to create a user account."""

    model_config = ConfigDict(extra="forbid")

    first_name: Annotated[str, Field(max_length=50)]
    mid_name: Annotated[str | None, Field(default=None, max_length=50)]
    last_name: Annotated[str, Field(max_length=50)]
    email_id: Annotated[str, Field(max_length=50)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


class RegisterUserResponse(BaseModel):
    """Safe response returned after user registration."""

    user_id: int
    email_id: str
    message: str

class TokenResponse(BaseModel):
    """OAuth2 bearer token returned after successful authentication."""

    access_token: str
    token_type: str = "bearer"

class LogoutResponse(BaseModel):
    """Safe response returned after user logout."""

    user_id: int
    message: str


@router.post(
    "/registerUser",
    response_model=RegisterUserResponse,
    status_code=status.HTTP_201_CREATED,
)
async def register_user(
    user_data: RegisterUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterUserResponse:
    """Hash a new user's password and save the user record in MySQL."""
    existing_user = await db.scalar(select(User).where(User.email_id == user_data.email_id))
    if existing_user is not None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A user with this email address already exists.",
        )

    user = User(
        first_name=user_data.first_name,
        mid_name=user_data.mid_name,
        last_name=user_data.last_name,
        email_id=user_data.email_id,
        hashed_password=hash_password(user_data.password),
    )
    db.add(user)

    try:
        await db.commit()
        await db.refresh(user)
    except Exception:
        await db.rollback()
        raise

    return RegisterUserResponse(
        user_id=user.user_id,
        email_id=user.email_id,
        message="User registered successfully.",
    )

@router.post(
    "/login",
    response_model=TokenResponse,
    status_code=status.HTTP_200_OK,
)
async def login_user(
    form_data: Annotated[OAuth2PasswordRequestForm, Depends()],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> TokenResponse:
    """Authenticate an email/password pair and issue an OAuth2 bearer token."""
    existing_user = await db.scalar(select(User).where(User.email_id == form_data.username))
    if existing_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    allow_user = verify_password(
        password=form_data.password,
        hashed_password=existing_user.hashed_password,
    )
    if not allow_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
            headers={"WWW-Authenticate": "Bearer"},
        )

    access_token,jti =create_access_token(subject=existing_user.user_id)

    start_time = datetime.now(timezone.utc)
    userSession = UserSession(
        user_id = existing_user.user_id,
        jti = jti,
        session_start = start_time,
        session_end = None
    )
    db.add(userSession)
    
    try:
        await db.commit()
        await db.refresh(userSession)
    except Exception:
        await db.rollback()
        raise
    return TokenResponse(
        access_token = access_token
    )

@router.post(
    "/logout",
    response_model=LogoutResponse,
    status_code=status.HTTP_200_OK,
)
async def logout_user(
    db: Annotated[AsyncSession, Depends(get_db)]
) -> LogoutResponse:
    current_user = get_current_user_id()
    if current_user is None:
        return LogoutResponse(
            user_id = current_user,
            message = "User Logged out successfully"
        )
    
    await db.execute(update(UserSession).where(UserSession.user_id == current_user).values(session_end=datetime.now(timezone.utc)))
    await db.commit()
    
    