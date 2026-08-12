from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_db
from app.database.models import User
from app.utils.utils import hash_password

router = APIRouter()


class RegisterUserRequest(BaseModel):
    """Body required to create a user account."""

    user_id: Annotated[int, Field(gt=0)]
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
        user_id=user_data.user_id,
        first_name=user_data.first_name,
        mid_name=user_data.mid_name,
        last_name=user_data.last_name,
        email_id=user_data.email_id,
        hashed_password=hash_password(user_data.password),
    )
    db.add(user)

    try:
        await db.commit()
    except Exception:
        await db.rollback()
        raise

    return RegisterUserResponse(
        user_id=user.user_id,
        email_id=user.email_id,
        message="User registered successfully.",
    )
