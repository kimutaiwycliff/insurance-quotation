"""Application-level encryption of sensitive PII (ADR-0018): national ID and passport numbers.

* AES-256-GCM with a random 96-bit nonce; the ciphertext is ``<key_id>:<base64(nonce|ciphertext|tag)>`` so keys
  can rotate (new writes use the first key; reads find the key by id).
* A keyed HMAC-SHA256 of the *normalised* value is stored next to it for exact-match lookup and duplicate
  detection, without decrypting or storing the plaintext.
* ``mask()`` is what lists and logs may show (last 3 characters).
"""

import base64
import hashlib
import hmac
import os
import re
from dataclasses import dataclass
from functools import cache

from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.core.config import Settings

KEY_BYTES = 32
NONCE_BYTES = 12


class CryptoConfigError(ValueError):
    pass


class DecryptionError(ValueError):
    pass


@dataclass(frozen=True)
class PiiCipher:
    keys: dict[str, AESGCM]
    active_key_id: str
    lookup_key: bytes

    def encrypt(self, plaintext: str) -> str:
        nonce = os.urandom(NONCE_BYTES)
        sealed = self.keys[self.active_key_id].encrypt(
            nonce, plaintext.encode(), self.active_key_id.encode()
        )
        return f"{self.active_key_id}:{base64.b64encode(nonce + sealed).decode()}"

    def decrypt(self, token: str) -> str:
        key_id, _, payload = token.partition(":")
        key = self.keys.get(key_id)
        if key is None or not payload:
            raise DecryptionError("Unknown encryption key")
        raw = base64.b64decode(payload)
        try:
            return key.decrypt(raw[:NONCE_BYTES], raw[NONCE_BYTES:], key_id.encode()).decode()
        except Exception:
            raise DecryptionError("Ciphertext could not be decrypted") from None

    def lookup_hash(self, value: str) -> str:
        return hmac.new(
            self.lookup_key, normalise_identifier(value).encode(), hashlib.sha256
        ).hexdigest()


def normalise_identifier(value: str) -> str:
    """ID/passport numbers compare without spaces, dashes and case."""
    return re.sub(r"[\s\-./]", "", value).upper()


def mask(value: str | None) -> str | None:
    if not value:
        return None
    clean = normalise_identifier(value)
    return f"{'•' * max(len(clean) - 3, 0)}{clean[-3:]}"


@cache
def _build(keys_spec: str, lookup_key: str) -> PiiCipher:
    keys: dict[str, AESGCM] = {}
    order: list[str] = []
    for entry in (e.strip() for e in keys_spec.split(",") if e.strip()):
        key_id, _, encoded = entry.partition(":")
        try:
            raw = base64.b64decode(encoded, validate=True)
        except ValueError:
            raw = b""
        if not key_id or len(raw) != KEY_BYTES:
            raise CryptoConfigError("PII_ENCRYPTION_KEYS entries must be key_id:base64(32 bytes)")
        keys[key_id] = AESGCM(raw)
        order.append(key_id)
    if not order:
        raise CryptoConfigError("PII_ENCRYPTION_KEYS is empty")
    if len(lookup_key) < KEY_BYTES:
        raise CryptoConfigError("PII_LOOKUP_KEY must be at least 32 characters")
    return PiiCipher(keys=keys, active_key_id=order[0], lookup_key=lookup_key.encode())


def pii_cipher(settings: Settings) -> PiiCipher:
    return _build(
        settings.pii_encryption_keys.get_secret_value(), settings.pii_lookup_key.get_secret_value()
    )
