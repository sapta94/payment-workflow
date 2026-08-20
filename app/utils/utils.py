import bcrypt


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
