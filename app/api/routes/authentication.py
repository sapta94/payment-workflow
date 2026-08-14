from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_db
from app.database.models import User
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

class LoginUserRequest(BaseModel):
    """Body required to login to a user account."""

    email_id: Annotated[str, Field(max_length=50)]
    password: Annotated[str, Field(min_length=8, max_length=128)]


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
    response_model=RegisterUserResponse,
    status_code=status.HTTP_200_OK,
)
async def login_user(
    user_data: LoginUserRequest,
    db: Annotated[AsyncSession, Depends(get_db)],
) -> RegisterUserResponse:
    existing_user = await db.scalar(select(User).where(User.email_id == user_data.email_id))
    if existing_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User Credentials Mismatch. Please verify your email or password.",
        )
    allow_user = verify_password(
        password=user_data.password,
        hashed_password=existing_user.hashed_password,
    )
    if not allow_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User Credentials Mismatch. Please verify your email or password.",
        )

    return RegisterUserResponse(
        user_id=existing_user.user_id,
        email_id=existing_user.email_id,
        message="User logged in successfully.",
    )
