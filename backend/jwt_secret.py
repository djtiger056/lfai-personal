"""JWT signing secret helpers for the personal edition."""

from __future__ import annotations

import secrets

from backend.config import config


MIN_HMAC_SECRET_BYTES = 32


def get_jwt_secret_key() -> str:
    """Return a JWT HMAC secret that satisfies PyJWT's HS256 key length check."""

    key = config.get("jwt_secret_key", "")
    if isinstance(key, str) and len(key.encode("utf-8")) >= MIN_HMAC_SECRET_BYTES:
        return key

    generated = secrets.token_urlsafe(48)
    config.update_config("jwt_secret_key", generated)
    return generated
