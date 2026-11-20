"""
Wrong passwords per account, on top of the login rate limit per IP.

LOGIN_THROTTLE_RATE slows down one address; guesses at one account from
many addresses are counted here, per username, under
LOGIN_ACCOUNT_THROTTLE_RATE. Once the count reaches the limit, the
username cannot log in, even with the right password, until the window
(the rate's period from the first wrong password) has passed. Usernames
without an account are counted the same, so the limit does not tell
which ones exist. The count lives in the TOKEN_CACHE.
"""

from django.core.cache import caches
from django.utils.crypto import salted_hmac

from .settings import cs_settings
from .throttling import parse_rate

KEY_PREFIX = "content_studio:login:fails"


def _cache():
    return caches[cs_settings.TOKEN_CACHE]


def _key(username: str) -> str:
    # Hashed: any username becomes a short key every cache backend takes.
    # Case-folded, so a username in other capitals is the same account
    # for user models that look emails up case-insensitively.
    digest = salted_hmac(
        "content_studio.login.failures", username.casefold(), algorithm="sha256"
    ).hexdigest()

    return f"{KEY_PREFIX}:{digest}"


def account_locked(username: str) -> bool:
    rate = cs_settings.LOGIN_ACCOUNT_THROTTLE_RATE

    if not rate:
        return False

    limit, _ = parse_rate(rate)

    return (_cache().get(_key(username)) or 0) >= limit


def count_failure(username: str) -> None:
    """A wrong password for the username, in a window of the rate's
    period from the first one."""
    rate = cs_settings.LOGIN_ACCOUNT_THROTTLE_RATE

    if not rate:
        return

    _, period = parse_rate(rate)
    cache = _cache()
    key = _key(username)
    cache.add(key, 0, period)

    try:
        cache.incr(key)
    except ValueError:
        cache.set(key, 1, period)


def clear_failures(username: str) -> None:
    """The right password: earlier mistakes no longer count."""
    if cs_settings.LOGIN_ACCOUNT_THROTTLE_RATE:
        _cache().delete(_key(username))
