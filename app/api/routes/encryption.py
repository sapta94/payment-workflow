from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.base import get_vault_db, get_db
from sqlalchemy import select
from app.core.encryption import encrypt_pan
from app.utils.utils import generate_card_token
from app.core.security import get_current_user_id

from app.database.models import CardVault, PaymentMethod, User

from app.utils.utils import detect_card_brand

from pydantic import BaseModel, Field, field_validator

router = APIRouter()


class CardDetailsRequest(BaseModel):
    """
    Request model for adding a card to the Card Vault.

    IMPORTANT:
    The PAN and CVV should only reach this endpoint.
    Other payment services should work with the generated token.
    """

    card_number: str = Field(
        ...,
        min_length=13,
        max_length=19,
        description="Credit/debit card PAN",
    )

    exp_month: int = Field(
        ...,
        ge=1,
        le=12,
    )

    exp_year: int = Field(
        ...,
        ge=2026,
        le=2100,
    )

    cvv: str = Field(
        ...,
        min_length=3,
        max_length=4,
    )

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, value: str) -> str:
        """
        Remove spaces/hyphens from the PAN.

        Example:

        4111 1111 1111 1111
                     ↓
        4111111111111111
        """

        value = value.replace(" ", "").replace("-", "")

        if not value.isdigit():
            raise ValueError("Card number must contain only digits")

        return value

    @field_validator("cvv")
    @classmethod
    def validate_cvv(cls, value: str) -> str:
        """
        CVV is never stored.

        We only validate that it consists of 3 or 4 digits.
        """

        if not value.isdigit():
            raise ValueError("CVV must contain only digits")

        return value


class CardTokenResponse(BaseModel):
    """
    Response returned to the client.

    Notice that the actual PAN and CVV are NEVER returned.
    """

    token: str
    card_brand: str
    last4: str
    exp_month: int
    exp_year: int

class CardDetailsRequest(BaseModel):
    """
    Request model for adding a card to the Card Vault.

    IMPORTANT:
    The PAN and CVV should only reach this endpoint.
    Other payment services should work with the generated token.
    """

    card_number: str = Field(
        ...,
        min_length=13,
        max_length=19,
        description="Credit/debit card PAN",
    )

    exp_month: int = Field(
        ...,
        ge=1,
        le=12,
    )

    exp_year: int = Field(
        ...,
        ge=2026,
        le=2100,
    )

    cvv: str = Field(
        ...,
        min_length=3,
        max_length=4,
    )

    @field_validator("card_number")
    @classmethod
    def validate_card_number(cls, value: str) -> str:
        """
        Remove spaces/hyphens from the PAN.

        Example:

        4111 1111 1111 1111
                     ↓
        4111111111111111
        """

        value = value.replace(" ", "").replace("-", "")

        if not value.isdigit():
            raise ValueError("Card number must contain only digits")

        return value

    @field_validator("cvv")
    @classmethod
    def validate_cvv(cls, value: str) -> str:
        """
        CVV is never stored.

        We only validate that it consists of 3 or 4 digits.
        """

        if not value.isdigit():
            raise ValueError("CVV must contain only digits")

        return value


class CardTokenResponse(BaseModel):
    """
    Response returned to the client.

    Notice that the actual PAN and CVV are NEVER returned.
    """

    token: str
    card_brand: str
    last4: str
    exp_month: int
    exp_year: int


class PaymentMethodRequest(BaseModel):
    """Request model to create a Payment method, mapping card details to an user"""
    token: str

class PaymentMethodResponse(BaseModel):
    """Safe response returned after user payment method mapping."""
    message: str

class GetCardsResponse(BaseModel):
    cards: list[CardTokenResponse]
    message: str

@router.post(
    "/cards",
    response_model=CardTokenResponse,
    status_code=status.HTTP_201_CREATED,
)
async def tokenize_card(
    card: CardDetailsRequest,
    db: Annotated[AsyncSession, Depends(get_vault_db)],
) -> CardTokenResponse:
    """
    Tokenize and securely store card information.

    Flow:

        Client
          |
          | PAN + expiry + CVV
          v
        Card Vault
          |
          +--> Generate random token
          |
          +--> Encrypt PAN using AES-256-GCM
          |
          +--> Store encrypted PAN
          |
          +--> DO NOT store CVV
          |
          v
        Return token

    The raw PAN should NOT be logged.
    The raw CVV should NEVER be logged or stored.
    """

    # ---------------------------------------------------------
    # 1. PAN is available only inside this vault operation.
    # ---------------------------------------------------------

    pan = card.card_number

    # ---------------------------------------------------------
    # 2. Detect card brand.
    #
    # This happens before storing anything.
    # ---------------------------------------------------------

    card_brand = detect_card_brand(pan)

    # ---------------------------------------------------------
    # 3. Generate a cryptographically secure random token.
    #
    # The token has NO mathematical relationship to the PAN.
    # ---------------------------------------------------------

    token = generate_card_token()

    # ---------------------------------------------------------
    # 4. Encrypt the PAN.
    #
    # The database will NEVER receive the raw PAN.
    # ---------------------------------------------------------

    encrypted_pan = encrypt_pan(pan)

    # ---------------------------------------------------------
    # 5. Store only the information required by CardVault.
    #
    # Notice that CVV is completely absent.
    #
    # CVV is NOT stored.
    # ---------------------------------------------------------

    card_vault_record = CardVault(
        token=token,
        encrypted_pan=encrypted_pan,
        card_brand=card_brand,
        exp_month=card.exp_month,
        exp_year=card.exp_year,

        # Only the last 4 digits are retained for display.
        last4=pan[-4:],
    )

    # ---------------------------------------------------------
    # 6. Persist the encrypted record.
    # ---------------------------------------------------------

    db.add(card_vault_record)

    await db.commit()

    # ---------------------------------------------------------
    # 7. Return only the tokenized representation.
    #
    # NEVER return:
    #
    #     card_number
    #     encrypted_pan
    #     cvv
    #
    # The rest of the application should use this token.
    # ---------------------------------------------------------

    return CardTokenResponse(
        token=token,
        card_brand=card_brand,
        last4=pan[-4:],
        exp_month=card.exp_month,
        exp_year=card.exp_year,
    )


@router.post(
    "/payment_method",
    response_model=PaymentMethodResponse,
    status_code=status.HTTP_200_OK,
)
async def add_payment_method(
    data: PaymentMethodRequest,
    current_user: Annotated[str, Depends(get_current_user_id)],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> PaymentMethodResponse:
    """
    Map a card token against the current user_id
    """

    paymentMethod = PaymentMethod(
        user_id = current_user,
        token = data.token
    )

    db.add(paymentMethod)
    
    try:
        await db.commit()
        await db.refresh(paymentMethod)
    except Exception:
        await db.rollback()
        raise

    return PaymentMethodResponse(
        message="Card Successfully Saved"
    )

@router.get(
    "/cards",
    response_model=GetCardsResponse,
    status_code=status.HTTP_200_OK
) 
async def get_card_details(
    current_user : Annotated[str, Depends(get_current_user_id)],
    db : Annotated[AsyncSession, Depends(get_db)],
    vault_db : Annotated[AsyncSession, Depends(get_vault_db)]
) -> GetCardsResponse:
    """
    Fetch ALl Saved cards of an User
    """
    result = await db.scalars( select(PaymentMethod).where( PaymentMethod.user_id == current_user ) ) 
    payment_methods = result.all()
    if not payment_methods: 
        return GetCardsResponse( 
            cards=[], 
            message="No Saved Payment Methods Found"
        )

    tokens = [ payment_method.token for payment_method in payment_methods ]
   
    card_details = await vault_db.scalars(select(CardVault).where(CardVault.token.in_(tokens)))
    card_details = card_details.all()

    all_cards = [ 
        CardTokenResponse( token=card.token, card_brand=card.card_brand, last4=card.last4, exp_month=card.exp_month, exp_year=card.exp_year) 
        for card in card_details 
        ]

    if all_cards is None:
        return GetCardsResponse(
            cards = [],
            message = "No Saved Payments Methods Found"
        )

    return GetCardsResponse(
                cards = all_cards,
                message = "Payment Methods Found"
            )