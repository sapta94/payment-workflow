from app.utils.utils import hash_password, verify_password


def test_hash_password_returns_a_non_reversible_hash() -> None:
    password = "secure-password"

    password_hash = hash_password(password)

    assert password_hash != password
    assert verify_password(password, password_hash)


def test_verify_password_rejects_an_incorrect_password() -> None:
    password_hash = hash_password("correct-password")

    assert not verify_password("incorrect-password", password_hash)


def test_verify_password_rejects_an_invalid_hash() -> None:
    assert not verify_password("password", "not-a-valid-hash")
