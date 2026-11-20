"""
The signed values that carry a login from the password to the code
step, and a new secret from the QR code to its confirmation.

A challenge names the user and a fingerprint of their password (so a
password change voids it), lives 5 minutes and works once. Wrong codes
count per challenge (5 send the editor back to the password) and per
account (TWO_FACTOR_THROTTLE_RATE), in the TOKEN_CACHE.
"""

import secrets

from django.contrib.auth import get_user_model
from django.core import signing
from django.core.cache import caches
from django.utils.crypto import constant_time_compare, salted_hmac

from ...settings import cs_settings
from ...throttling import parse_rate

CHALLENGE_SALT = "content_studio.two_factor.challenge"
SETUP_SALT = "content_studio.two_factor.setup"
CHALLENGE_MAX_AGE = 5 * 60
SETUP_MAX_AGE = 15 * 60
MAX_TRIES = 5

KEY_PREFIX = "content_studio:two_factor"


class InvalidChallenge(Exception):
    pass


def _cache():
    return caches[cs_settings.TOKEN_CACHE]


def _password_fingerprint(user) -> str:
    return salted_hmac(CHALLENGE_SALT, user.password, algorithm="sha256").hexdigest()[
        :16
    ]


def make_challenge(user) -> str:
    return signing.dumps(
        {
            "u": str(user.pk),
            "p": _password_fingerprint(user),
            "n": secrets.token_hex(16),
        },
        salt=CHALLENGE_SALT,
    )


def read_challenge(value):
    """The challenge's user and nonce; InvalidChallenge when it does not
    work (expired, used, too many wrong codes, password changed)."""
    from ...password_links import can_log_in

    try:
        data = signing.loads(value, salt=CHALLENGE_SALT, max_age=CHALLENGE_MAX_AGE)
        user = get_user_model()._default_manager.get(pk=data["u"])
    except Exception:
        raise InvalidChallenge()

    if not can_log_in(user) or not constant_time_compare(
        data["p"], _password_fingerprint(user)
    ):
        raise InvalidChallenge()

    nonce = data["n"]
    cache = _cache()

    if cache.get(f"{KEY_PREFIX}:used:{nonce}"):
        raise InvalidChallenge()

    if (cache.get(f"{KEY_PREFIX}:tries:{nonce}") or 0) >= MAX_TRIES:
        raise InvalidChallenge()

    return user, nonce


def use_challenge(nonce) -> bool:
    """Mark the challenge used; False when another request used it."""
    return _cache().add(f"{KEY_PREFIX}:used:{nonce}", True, CHALLENGE_MAX_AGE + 1)


def count_wrong_code(nonce) -> int:
    """Count a wrong code against the challenge; the tries left."""
    cache = _cache()
    key = f"{KEY_PREFIX}:tries:{nonce}"
    cache.add(key, 0, CHALLENGE_MAX_AGE + 1)

    try:
        tries = cache.incr(key)
    except ValueError:
        tries = 1
        cache.set(key, tries, CHALLENGE_MAX_AGE + 1)

    return max(MAX_TRIES - tries, 0)


# Kept for imports of the old name.
_parse_rate = parse_rate


def account_locked(user) -> bool:
    rate = cs_settings.TWO_FACTOR_THROTTLE_RATE

    if not rate:
        return False

    limit, _ = _parse_rate(rate)

    return (_cache().get(f"{KEY_PREFIX}:fails:{user.pk}") or 0) >= limit


def count_account_failure(user) -> None:
    """A wrong code for the account, in a window of the rate's period
    from the first one."""
    rate = cs_settings.TWO_FACTOR_THROTTLE_RATE

    if not rate:
        return

    _, period = _parse_rate(rate)
    cache = _cache()
    key = f"{KEY_PREFIX}:fails:{user.pk}"
    cache.add(key, 0, period)

    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, period)


def make_setup_token(user, secret: str, nonce: str = "") -> str:
    """The new secret, signed for the user (and the login's challenge),
    until a code from the app confirms it."""
    return signing.dumps({"u": str(user.pk), "s": secret, "n": nonce}, salt=SETUP_SALT)


def read_setup_token(value, user, nonce: str = "") -> str:
    """The secret of a setup token for this user; InvalidChallenge when
    it is not theirs or has expired."""
    try:
        data = signing.loads(value, salt=SETUP_SALT, max_age=SETUP_MAX_AGE)
    except Exception:
        raise InvalidChallenge()

    if data.get("u") != str(user.pk) or data.get("n", "") != nonce:
        raise InvalidChallenge()

    return data["s"]
