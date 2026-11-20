import secrets

from django.conf import settings
from django.db import models
from django.utils.crypto import constant_time_compare, salted_hmac
from django.utils.translation import gettext_lazy as _

AUTHENTICATOR_RELATED_NAME = "content_studio_authenticator"

RECOVERY_CODE_COUNT = 10
# Letters and digits that cannot be mistaken for one another.
RECOVERY_ALPHABET = "abcdefghjkmnpqrstuvwxyz23456789"


class Authenticator(models.Model):
    """
    A user's authenticator app: the TOTP secret it shares. One per user;
    passkeys would get a model of their own.

    The secret has to be readable to check codes, so it is stored as is,
    as django-otp does. Protect the database (or encrypt it) accordingly.
    """

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name=AUTHENTICATOR_RELATED_NAME,
        verbose_name=_("user"),
    )
    secret = models.CharField(_("secret"), max_length=64)
    created_at = models.DateTimeField(_("created at"), auto_now_add=True)
    last_used_at = models.DateTimeField(_("last used at"), null=True, blank=True)
    # The step of the last code used: a code works only once.
    last_step = models.BigIntegerField(default=0)

    class Meta:
        verbose_name = _("authenticator")
        verbose_name_plural = _("authenticators")

    def __str__(self):
        return str(self.user)


class RecoveryCode(models.Model):
    """
    A single-use code that logs in without the app. Only an HMAC of the
    code is kept (keyed with SECRET_KEY), so a copy of the database does
    not reveal the codes.
    """

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="content_studio_recovery_codes",
        verbose_name=_("user"),
    )
    code_hash = models.CharField(max_length=64)
    used_at = models.DateTimeField(_("used at"), null=True, blank=True)

    class Meta:
        verbose_name = _("recovery code")
        verbose_name_plural = _("recovery codes")

    def __str__(self):
        return str(self.user)


def get_authenticator(user):
    """The user's authenticator, or None; read with select_related when
    the user came from content_studio.login.user_queryset()."""
    if user is None or getattr(user, "pk", None) is None:
        return None

    try:
        return getattr(user, AUTHENTICATOR_RELATED_NAME)
    except Authenticator.DoesNotExist:
        return None


def normalize_recovery_code(code: str) -> str:
    return "".join(c for c in (code or "").lower() if c.isalnum())


def hash_recovery_code(code: str, secret=None) -> str:
    return salted_hmac(
        "content_studio.two_factor.recovery_code",
        normalize_recovery_code(code),
        secret=secret,
        algorithm="sha256",
    ).hexdigest()


def recovery_code_matches(code: str, code_hash: str) -> bool:
    """Checked with SECRET_KEY and its SECRET_KEY_FALLBACKS."""
    keys = [settings.SECRET_KEY, *(getattr(settings, "SECRET_KEY_FALLBACKS", []) or [])]

    return any(
        constant_time_compare(hash_recovery_code(code, key), code_hash) for key in keys
    )


def generate_recovery_code() -> str:
    """Like "k7f2-9xqa": about 40 random bits."""
    chars = "".join(secrets.choice(RECOVERY_ALPHABET) for _ in range(8))

    return f"{chars[:4]}-{chars[4:]}"
