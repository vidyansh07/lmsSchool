"""Encrypting the secrets an outbound webhook carries.

Fernet under `INTEGRATION_ENCRYPTION_KEY`, falling back to the MFA key so a
deployment that already has one does not need a second before it can save a
webhook. Neither has a production default (see `config/settings/hardened.py`).
"""

from __future__ import annotations

import json

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured


def _fernet() -> Fernet:
    key = getattr(settings, "INTEGRATION_ENCRYPTION_KEY", "") or getattr(
        settings, "MFA_ENCRYPTION_KEY", ""
    )
    if not key:
        raise ImproperlyConfigured(
            "INTEGRATION_ENCRYPTION_KEY (or MFA_ENCRYPTION_KEY) is not configured."
        )
    return Fernet(key.encode("utf-8") if isinstance(key, str) else key)


def encrypt(value: str) -> str:
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii") if value else ""


def decrypt(token: str) -> str:
    if not token:
        return ""
    try:
        return _fernet().decrypt(token.encode("ascii")).decode("utf-8")
    except InvalidToken:
        return ""


def encrypt_json(value: dict) -> str:
    return encrypt(json.dumps(value)) if value else ""


def decrypt_json(token: str) -> dict:
    raw = decrypt(token)
    try:
        value = json.loads(raw) if raw else {}
    except ValueError:
        return {}
    return value if isinstance(value, dict) else {}
