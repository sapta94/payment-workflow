import base64
import os

from cryptography.hazmat.primitives.ciphers.aead import AESGCM


# The encryption key must come from a secure environment variable
# or, preferably in production, a KMS/HSM.
#
# DO NOT store this key in MySQL.
#
# The key must be exactly 32 bytes for AES-256.
ENCRYPTION_KEY = base64.b64decode(
    os.environ["CARD_VAULT_ENCRYPTION_KEY"]
)


def encrypt_pan(pan: str) -> str:
    """
    Encrypt the PAN using AES-256-GCM.

    AES-GCM provides:
        1. Confidentiality
        2. Integrity/authentication

    A new random nonce is generated for every encryption operation.
    """

    aesgcm = AESGCM(ENCRYPTION_KEY)

    # AES-GCM commonly uses a 12-byte nonce.
    nonce = os.urandom(12)

    encrypted_data = aesgcm.encrypt(
        nonce,
        pan.encode("utf-8"),
        None,
    )

    # We need to store both the nonce and encrypted data.
    #
    # The nonce does NOT need to be secret.
    # It only needs to be unique for a given encryption key.
    encrypted_value = nonce + encrypted_data

    # Database stores the result as text.
    return base64.b64encode(
        encrypted_value
    ).decode("utf-8")


def decrypt_pan(encrypted_pan: str) -> str:
    """
    Decrypt a PAN.

    This function should be used ONLY by the component
    that genuinely needs the PAN.

    Normal application services should never need to call this.
    """

    aesgcm = AESGCM(ENCRYPTION_KEY)

    encrypted_value = base64.b64decode(
        encrypted_pan
    )

    # First 12 bytes are the nonce.
    nonce = encrypted_value[:12]

    # Remaining bytes are the encrypted PAN + GCM authentication tag.
    ciphertext = encrypted_value[12:]

    decrypted_pan = aesgcm.decrypt(
        nonce,
        ciphertext,
        None,
    )

    return decrypted_pan.decode("utf-8")