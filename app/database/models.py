from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum as pyenum

from sqlalchemy import (
    TIMESTAMP,
    BigInteger,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database.base import Base


class UserType(str, pyenum):
    USER = "USER"
    MERCHANT = "MERCHANT"


class PaymentStatus(str, pyenum):
    CREATED = "CREATED"
    PROCESSING = "PROCESSING"
    SUCCESS = "SUCCESS"
    FAILED = "FAILED"
    CANCELLED = "CANCELLED"
    REFUNDED = "REFUNDED"


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
    user_type: Mapped[UserType] = mapped_column(
        Enum(UserType, native_enum=False),
        default=UserType.USER,
    )


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

class PaymentMethod(Base):
    __tablename__ = "user_payment_methods"

    payment_method_id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(
            ForeignKey("user_list.user_id")
        )
    token: Mapped[str] = mapped_column(
        String(100),
        nullable=False,
    )


class Merchant(Base):
    """Business profile owned by a user with the MERCHANT account type."""

    __tablename__ = "merchant_list"

    merchant_id: Mapped[int] = mapped_column(
        ForeignKey("user_list.user_id"),
        primary_key=True,
    )
    business_name: Mapped[str] = mapped_column(String(255), nullable=False)
    business_address: Mapped[str] = mapped_column(String(500), nullable=False)
    city: Mapped[str | None] = mapped_column(String(100))
    state: Mapped[str | None] = mapped_column(String(100))
    country: Mapped[str | None] = mapped_column(String(100))
    postal_code: Mapped[str | None] = mapped_column(String(20))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc),nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=False)

class MerchantBank(Base):
    """Bank details of a user with the MERCHANT account type."""

    __tablename__ = "merchant_vault"
    
    
    merchant_id: Mapped[int] = mapped_column(
            primary_key=True,
        )
    encrypted_tin: Mapped[str] = mapped_column(String(500), nullable=False)
    encrypted_bank_account: Mapped[str] = mapped_column(String(1000), nullable=False)
    encrypted_routing_number: Mapped[str] = mapped_column(String(500),  nullable=False)
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc),nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=False)


class Payment(Base):
    """A payment transaction stored in the PayE payment table."""

    __tablename__ = "payment"
    __table_args__ = (
        Index("uk_payment_idempotency", "user_id", "idempotency_key", unique=True),
        Index("idx_payment_user", "user_id"),
        Index("idx_payment_merchant", "merchant_id"),
        Index("idx_payment_method", "payment_method_id"),
        Index("idx_payment_status", "payment_status"),
        Index("idx_provider_payment", "transaction_id"),
    )

    payment_id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    merchant_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    payment_method_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2), nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    payment_status: Mapped[PaymentStatus] = mapped_column(
        Enum(PaymentStatus, native_enum=True),
        nullable=False,
        default=PaymentStatus.CREATED,
    )
    provider: Mapped[str | None] = mapped_column(String(30))
    transaction_id: Mapped[str | None] = mapped_column(String(100))
    idempotency_key: Mapped[str] = mapped_column(String(100), nullable=False)
    failure_code: Mapped[str | None] = mapped_column(String(100))
    failure_message: Mapped[str | None] = mapped_column(String(500))
    created_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, default=datetime.now(timezone.utc),nullable=False)
    updated_at: Mapped[datetime | None] = mapped_column(TIMESTAMP, nullable=False)