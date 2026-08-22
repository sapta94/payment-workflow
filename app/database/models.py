from datetime import datetime

from sqlalchemy import TIMESTAMP, ForeignKey, Index, Integer, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class User(Base):
    """A user record stored in the user_list MySQL table."""

    __tablename__ = "user_list"
    __table_args__ = (Index("email_idx", "email_id"),)

    user_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    first_name: Mapped[str | None] = mapped_column(String(50))
    mid_name: Mapped[str | None] = mapped_column(String(50))
    last_name: Mapped[str | None] = mapped_column(String(50))
    email_id: Mapped[str | None] = mapped_column(String(50))
    hashed_password: Mapped[str | None] = mapped_column("password", String(255))


class UserSession(Base):
    """A session record for a user and a JWT identifier."""

    __tablename__ = "user_sessions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("user_list.user_id"),
        primary_key=True,
    )
    jti: Mapped[str] = mapped_column(String(255), primary_key=True)
    session_start: Mapped[datetime | None] = mapped_column(TIMESTAMP)
    session_end: Mapped[datetime | None] = mapped_column(TIMESTAMP)

class CardVault(Base):
    __tablename__ = "card_vault"

    # Randomly generated token.
    # This is what other services should use instead of the PAN.
    token: Mapped[str] = mapped_column(
        String(100),
        primary_key=True,
        nullable=False,
    )

    # AES-GCM encrypted PAN.
    #
    # IMPORTANT:
    # The encryption key is NOT stored in this table.
    encrypted_pan: Mapped[str] = mapped_column(
        String(500),
        nullable=False,
    )

    card_brand: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
    )

    exp_month: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    exp_year: Mapped[int] = mapped_column(
        Integer,
        nullable=False,
    )

    # Storing last 4 digits is useful for displaying:
    # "Visa ending in 1111"
    #
    # This is NOT the PAN.
    last4: Mapped[str] = mapped_column(
        String(4),
        nullable=False,
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )
