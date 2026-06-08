"""
admin_auth.py - eenvoudige admin-login voor de website
======================================================
Eén gedeeld admin-wachtwoord (uit secrets.h: ADMIN_PASSWORD). Na een geldige
login krijgt de browser een sessie-token (bewaard in localStorage) dat als
'Authorization: Bearer <token>' meegestuurd wordt bij wijzig-acties.

Publieke (GET) endpoints blijven open; alle wijzig-endpoints checken via de
require_admin-dependency of het token geldig is.
"""

from __future__ import annotations

import hmac
import secrets as _secrets
import threading
import time

from secrets_loader import load_secrets

SESSION_TTL = 12 * 3600  # tokens 12 uur geldig

_sessions: dict[str, float] = {}  # token -> verloopt op (epoch)
_lock = threading.Lock()


def _admin_password() -> str:
    return load_secrets().get("ADMIN_PASSWORD", "") or ""


def is_configured() -> bool:
    """Is er een admin-wachtwoord ingesteld?"""
    return bool(_admin_password())


def login(password: str) -> str | None:
    """Geef een nieuw sessie-token terug bij correct wachtwoord, anders None."""
    expected = _admin_password()
    if not expected:
        return None
    if not hmac.compare_digest(password or "", expected):
        return None
    token = _secrets.token_urlsafe(32)
    with _lock:
        _sessions[token] = time.time() + SESSION_TTL
        _prune()
    return token


def validate(token: str | None) -> bool:
    if not token:
        return False
    with _lock:
        expiry = _sessions.get(token)
        if expiry is None:
            return False
        if expiry < time.time():
            _sessions.pop(token, None)
            return False
        return True


def logout(token: str | None) -> None:
    if not token:
        return
    with _lock:
        _sessions.pop(token, None)


def _prune() -> None:
    now = time.time()
    for tok in [t for t, exp in _sessions.items() if exp < now]:
        _sessions.pop(tok, None)


def token_from_header(authorization: str | None) -> str | None:
    if authorization and authorization.lower().startswith("bearer "):
        return authorization[7:].strip()
    return None
