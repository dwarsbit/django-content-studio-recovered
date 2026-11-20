"""
Time-based one-time passwords (RFC 6238): the six-digit codes of
authenticator apps, with HMAC-SHA1 and 30-second steps, as every app
supports. Written with the standard library; tests check it against the
RFC's test vectors.
"""

import base64
import hashlib
import hmac
import secrets
import struct
import time
from typing import Optional
from urllib.parse import quote, urlencode

DIGITS = 6
STEP = 30
# Codes of the step before and after the current one are accepted, for
# phones whose clock is a little off.
WINDOW = 1


def generate_secret() -> str:
    """A new secret: 160 random bits in base32, as RFC 4226 advises."""
    return base64.b32encode(secrets.token_bytes(20)).decode("ascii").rstrip("=")


def _key(secret: str) -> bytes:
    secret = secret.replace(" ", "").upper()

    return base64.b32decode(secret + "=" * (-len(secret) % 8))


def hotp(key: bytes, counter: int, digits: int = DIGITS) -> str:
    """RFC 4226: the code for a counter."""
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    value = struct.unpack(">I", digest[offset : offset + 4])[0] & 0x7FFFFFFF

    return str(value % 10**digits).zfill(digits)


def current_step(now: Optional[float] = None) -> int:
    return int((time.time() if now is None else now) // STEP)


def code_at(secret: str, step: int) -> str:
    return hotp(_key(secret), step)


def match_step(
    secret: str, code: str, *, after: int = 0, now: Optional[float] = None
) -> Optional[int]:
    """
    The step whose code the code is, within the window around now and
    later than after (a code works once); None when it matches none.
    """
    code = (code or "").replace(" ", "")

    if len(code) != DIGITS or not code.isdigit():
        return None

    key = _key(secret)
    step = current_step(now)

    for candidate in range(step - WINDOW, step + WINDOW + 1):
        if candidate > after and hmac.compare_digest(hotp(key, candidate), code):
            return candidate

    return None


def provisioning_uri(secret: str, account: str, issuer: str) -> str:
    """The otpauth:// link an app reads from the QR code."""
    label = quote(f"{issuer}:{account}" if issuer else account, safe="@:")
    query = {"secret": secret, "digits": DIGITS, "period": STEP}

    if issuer:
        query["issuer"] = issuer

    return f"otpauth://totp/{label}?{urlencode(query, quote_via=quote)}"
