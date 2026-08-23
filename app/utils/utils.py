import bcrypt
import secrets


def hash_password(password: str) -> str:
    """Hash a plain-text password with bcrypt for safe database storage."""
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, hashed_password: str) -> bool:
    """Return whether a plain-text password matches its bcrypt hash."""
    try:
        return bcrypt.checkpw(
            password.encode("utf-8"),
            hashed_password.encode("utf-8"),
        )
    except ValueError:
        # A malformed or unsupported hash must never authenticate a user.
        return False
import secrets


def generate_card_token() -> str:
    """
    Generate a cryptographically secure random card token.

    IMPORTANT:

    The token is NOT derived from the PAN.

    We intentionally do NOT do:

        SHA256(PAN)

    or:

        MD5(PAN)

    or:

        encryption(PAN)

    as the token.

    The token is an independent random identifier.
    """

    random_part = secrets.token_urlsafe(32)

    return f"ctok_{random_part}"

def detect_card_brand(card_number: str) -> str:
    """
    Basic card-brand detection.

    This is intentionally simplified for the project.
    A production payment system should use a proper BIN/IIN
    database/service rather than relying solely on these rules.
    """

    if card_number.startswith("4"):
        return "VISA"

    if (
        card_number.startswith("51")
        or card_number.startswith("52")
        or card_number.startswith("53")
        or card_number.startswith("54")
        or card_number.startswith("55")
    ):
        return "MASTERCARD"

    if card_number.startswith("34") or card_number.startswith("37"):
        return "AMEX"

    if card_number.startswith("6011"):
        return "DISCOVER"

    return "UNKNOWN"