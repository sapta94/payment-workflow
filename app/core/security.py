from datetime import datetime, timedelta, timezone
from typing import Annotated

import jwt
import uuid
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jwt.exceptions import InvalidTokenError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.database.base import get_db

from app.core.config import get_settings
from app.database.models import UserSession

settings = get_settings()

oauth2_scheme = OAuth2PasswordBearer(tokenUrl=f"{settings.api_v1_prefix}/auth/login")


def create_access_token(subject: str) -> tuple:
    """Create a signed, short-lived access token for an authenticated user."""
    expires_at = datetime.now(timezone.utc) + timedelta(
        minutes=settings.access_token_expire_minutes,
    )
    token_id = str(uuid.uuid4())
    return jwt.encode(
        {"sub": str(subject), "jti":token_id, "exp": expires_at},
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    ), token_id


async def get_current_user_id(
    token: Annotated[str, Depends(oauth2_scheme)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> str:
    """Validate bearer token and return the authenticated user's ID."""

    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials.",
        headers={"WWW-Authenticate": "Bearer"},
    )

    try:
        # Decode JWT
        payload = jwt.decode(
            token,
            settings.jwt_secret_key,
            algorithms=[settings.jwt_algorithm],
        )

        # Get user ID from JWT
        user_id = payload.get("sub")

        if not isinstance(user_id, str):
            raise credentials_exception

        # Get JWT ID
        jti = payload.get("jti")

        if not isinstance(jti, str):
            raise credentials_exception

        # Check whether this session exists
        active_user = await db.scalar(
            select(UserSession)
            .where(UserSession.jti == jti)
        )

        # Session doesn't exist
        if active_user is None:
            raise credentials_exception

        session_end = active_user.session_end

        if session_end is not None:

            # MySQL returns a naive datetime
            # Treat it as UTC
            if session_end.tzinfo is None:
                session_end = session_end.replace(tzinfo=timezone.utc)

            if session_end <= datetime.now(timezone.utc):
                raise credentials_exception

        return user_id

    except InvalidTokenError as error:
        raise credentials_exception from error