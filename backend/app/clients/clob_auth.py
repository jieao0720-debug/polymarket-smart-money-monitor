"""CLOB L2 (API-key) auth header construction.

HMAC-SHA256 over `timestamp + method + path + body`, secret is base64url-decoded,
digest base64url-encoded — matching the official py-clob-client implementation.

SECURITY: credentials live only in function arguments for the duration of one request.
They are never persisted, never logged (logging_utils redacts these key names), and
never echoed back in responses. UNCERTAINTY-U10: live verification pending; this path
is unreachable unless ENABLE_LIVE_TRADING=true.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ClobCredentials:
    api_key: str
    secret: str
    passphrase: str


def build_l1_headers(*, wallet_address: str, signature: str, timestamp: int,
                     nonce: int = 0) -> dict[str, str]:
    """L1 headers: the EIP-712 `ClobAuth` signature is produced by the USER'S WALLET in
    the frontend — the backend only forwards it and never sees a private key."""
    return {
        "POLY_ADDRESS": wallet_address,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": str(timestamp),
        "POLY_NONCE": str(nonce),
    }


def build_l2_headers(*, credentials: ClobCredentials, wallet_address: str, method: str,
                     request_path: str, body: dict[str, Any] | None = None,
                     timestamp: int | None = None) -> dict[str, str]:
    ts = str(timestamp if timestamp is not None else int(time.time()))
    body_str = "" if body is None else json.dumps(body, separators=(",", ":"))
    message = ts + method.upper() + request_path + body_str
    secret_bytes = base64.urlsafe_b64decode(credentials.secret)
    digest = hmac.new(secret_bytes, message.encode("utf-8"), hashlib.sha256).digest()
    signature = base64.urlsafe_b64encode(digest).decode("utf-8")
    return {
        "POLY_ADDRESS": wallet_address,
        "POLY_SIGNATURE": signature,
        "POLY_TIMESTAMP": ts,
        "POLY_API_KEY": credentials.api_key,
        "POLY_PASSPHRASE": credentials.passphrase,
    }
