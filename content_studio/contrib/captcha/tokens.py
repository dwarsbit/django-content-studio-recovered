import hashlib
import secrets
from datetime import timedelta

from django.utils import timezone

from content_studio.settings import cs_settings

TOKEN_LIFETIME = timedelta(minutes=20)

# The longest token verify_captcha() looks up; a real one is 47 characters.
MAX_TOKEN_LENGTH = 100


def _digest(secret: str) -> str:
    return hashlib.sha256(secret.encode()).hexdigest()


def issue_token() -> tuple[str, int]:
    """A new token for a solved challenge, and when it expires in milliseconds since the epoch."""
    from .models import Token

    token_id, secret = secrets.token_hex(8), secrets.token_hex(15)
    expires_at = timezone.now() + TOKEN_LIFETIME
    Token.objects.create(id=token_id, digest=_digest(secret), expires_at=expires_at)
    return f"{token_id}:{secret}", int(expires_at.timestamp() * 1000)


def verify_captcha(token: object) -> bool:
    """
    Whether ``token`` is a token the widget redeemed, unused and not
    expired. A token is valid once: verifying it uses it up. With
    ``CONTENT_STUDIO["CAPTCHA"]`` off every token is valid.
    """
    if not cs_settings.CAPTCHA:
        return True
    from .models import Token

    if not isinstance(token, str) or len(token) > MAX_TOKEN_LENGTH:
        return False
    token_id, _, secret = token.partition(":")
    if not token_id or not secret:
        return False
    deleted, _ = Token.objects.filter(
        id=token_id, digest=_digest(secret), expires_at__gt=timezone.now()
    ).delete()
    return deleted > 0
