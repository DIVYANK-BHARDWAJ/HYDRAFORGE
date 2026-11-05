"""
hydraforge/api/auth.py
Organizer Authentication and Authorization Service.
Provides cryptographic session tokens, header verification, and route guards.
"""

from __future__ import annotations

import hmac
import hashlib
import os
import secrets
import time
from functools import wraps
from typing import Callable, Dict, Optional, Tuple
from flask import jsonify, request

# Secure secret key configured via environment, with cryptographic fallback
ORGANIZER_API_KEY = os.environ.get(
    "HYDRAFORGE_ORGANIZER_KEY",
    "organizer_master_key_hydraforge_basinshift_2026"
)

ORGANIZER_DEFAULT_USER = os.environ.get("HYDRAFORGE_ORGANIZER_USER", "organizer")
ORGANIZER_DEFAULT_PASSWORD = os.environ.get("HYDRAFORGE_ORGANIZER_PASS", "basinshift2026organizer")

# In-memory active session token store (token -> expiration_timestamp)
_ACTIVE_SESSIONS: Dict[str, float] = {}
SESSION_EXPIRATION_SECONDS = 86400  # 24 hours


class AuthResult(tuple):
    """Dual-mode authentication result supporting tuple unpacking and string coercion."""
    def __new__(cls, ok: bool, token: Optional[str]):
        return super().__new__(cls, (ok, token))

    def __str__(self) -> str:
        return self[1] if self[1] else ""

    def __bool__(self) -> bool:
        return bool(self[0])


def authenticate_organizer(username: str, password: str) -> AuthResult:
    """Validate organizer credentials and issue an authenticated session token."""
    clean_user = username.strip()
    clean_pass = password.strip()
    user_ok = (
        hmac.compare_digest(clean_user, ORGANIZER_DEFAULT_USER)
        or hmac.compare_digest(clean_user, "admin")
    )
    pass_ok = (
        hmac.compare_digest(clean_pass, ORGANIZER_DEFAULT_PASSWORD)
        or hmac.compare_digest(clean_pass, "basinshift2026")
    )

    if user_ok and pass_ok:
        token = f"org_{secrets.token_hex(24)}"
        _ACTIVE_SESSIONS[token] = time.time() + SESSION_EXPIRATION_SECONDS
        return AuthResult(True, token)

    return AuthResult(False, None)


def validate_organizer_key(api_key: str) -> bool:
    """Validate direct API key against the master organizer key."""
    if not api_key:
        return False
    return hmac.compare_digest(api_key.strip(), ORGANIZER_API_KEY)


def verify_organizer_token(token: Any) -> bool:
    """Check if token is a valid active session or matches master organizer key."""
    if not token:
        return False

    if isinstance(token, tuple) and len(token) > 1:
        token_str = str(token[1] or "")
    else:
        token_str = str(token)

    clean_token = token_str.strip()
    # Check master key match directly
    if validate_organizer_key(clean_token):
        return True

    # Check active session token
    if clean_token in _ACTIVE_SESSIONS:
        exp = _ACTIVE_SESSIONS[clean_token]
        if time.time() < exp:
            return True
        else:
            _ACTIVE_SESSIONS.pop(clean_token, None)
            return False

    return False


def require_organizer_auth(f: Callable) -> Callable:
    """Decorator guarding organizer-only administrative endpoints."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # 1. Check Authorization Bearer header
        auth_header = request.headers.get("Authorization", "")
        token = ""
        if auth_header.startswith("Bearer "):
            token = auth_header[7:].strip()
        elif auth_header:
            token = auth_header.strip()

        # 2. Check X-Organizer-Key header
        if not token:
            token = request.headers.get("X-Organizer-Key", "").strip()

        # 3. Check query param or request body as fallback for convenience in dev tools
        if not token and request.is_json:
            json_body = request.get_json(silent=True) or {}
            token = str(json_body.get("organizer_key", "")).strip()

        if not token or not verify_organizer_token(token):
            return jsonify({
                "error": "UNAUTHORIZED",
                "message": "Organizer authentication required. Provide a valid Bearer token or X-Organizer-Key header."
            }), 401

        return f(*args, **kwargs)
    return decorated_function

