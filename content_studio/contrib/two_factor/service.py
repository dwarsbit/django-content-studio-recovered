"""
Turning two-factor login on and off, checking codes, recovery codes.
"""

from typing import Optional

from django.db import transaction
from django.utils import timezone

from ...settings import cs_settings
from . import totp
from .models import (
    RECOVERY_CODE_COUNT,
    Authenticator,
    RecoveryCode,
    generate_recovery_code,
    get_authenticator,
    hash_recovery_code,
    normalize_recovery_code,
    recovery_code_matches,
)


def issuer() -> str:
    if cs_settings.TWO_FACTOR_ISSUER:
        return str(cs_settings.TWO_FACTOR_ISSUER)

    return str(getattr(cs_settings.ADMIN_SITE, "site_title", "") or "Content Studio")


def setup_data(user, secret: str) -> dict:
    """What an app needs to add the account: the secret and its link."""
    return {
        "secret": secret,
        "uri": totp.provisioning_uri(secret, user.get_username(), issuer()),
    }


def new_recovery_codes(user) -> list[str]:
    """Replace the user's recovery codes; the new ones are shown once."""
    codes = [generate_recovery_code() for _ in range(RECOVERY_CODE_COUNT)]

    with transaction.atomic():
        RecoveryCode.objects.filter(user=user).delete()
        RecoveryCode.objects.bulk_create(
            RecoveryCode(user=user, code_hash=hash_recovery_code(code))
            for code in codes
        )

    return codes


def enable(user, secret: str, code: str) -> Optional[list[str]]:
    """
    Turn two-factor login on with a secret the user's app confirmed with
    a code. Returns the recovery codes, or None when the code is wrong.
    """
    step = totp.match_step(secret, code)

    if step is None:
        return None

    with transaction.atomic():
        Authenticator.objects.filter(user=user).delete()
        authenticator = Authenticator.objects.create(
            user=user, secret=secret, last_step=step, last_used_at=timezone.now()
        )
        codes = new_recovery_codes(user)

    # The cached reverse relation: the session stamp reads it.
    user.content_studio_authenticator = authenticator

    return codes


def disable(user) -> bool:
    """Turn two-factor login off; whether it was on."""
    with transaction.atomic():
        deleted, _ = Authenticator.objects.filter(user=user).delete()
        RecoveryCode.objects.filter(user=user).delete()

    # Forget the cached relation, so the session stamp reads it again.
    user._state.fields_cache.pop("content_studio_authenticator", None)

    return bool(deleted)


def check_code(user, code: str) -> bool:
    """
    Whether the code is the app's current code, and not used before:
    using it records its step, so it does not work twice, even for two
    requests at once.
    """
    authenticator = get_authenticator(user)

    if authenticator is None:
        return False

    step = totp.match_step(authenticator.secret, code, after=authenticator.last_step)

    if step is None:
        return False

    # Only one of two requests with the same code moves the step on.
    used = Authenticator.objects.filter(pk=authenticator.pk, last_step__lt=step).update(
        last_step=step, last_used_at=timezone.now()
    )

    return bool(used)


def check_recovery_code(user, code: str) -> bool:
    """Whether the code is an unused recovery code; using it uses it up."""
    if not normalize_recovery_code(code):
        return False

    for recovery_code in RecoveryCode.objects.filter(user=user, used_at=None):
        if recovery_code_matches(code, recovery_code.code_hash):
            return bool(
                RecoveryCode.objects.filter(pk=recovery_code.pk, used_at=None).update(
                    used_at=timezone.now()
                )
            )

    return False


def state(user) -> dict:
    """The profile page's view of it."""
    from ...login import two_factor_required

    authenticator = get_authenticator(user)

    return {
        "enabled": authenticator is not None,
        "since": authenticator.created_at.isoformat() if authenticator else None,
        "recovery_codes_left": (
            RecoveryCode.objects.filter(user=user, used_at=None).count()
            if authenticator
            else 0
        ),
        "required": two_factor_required(user),
    }


def reset(user, request) -> bool:
    """
    An admin resets the user's two-factor login (a lost phone): it is
    off, their sessions end, and they get an email that it happened.
    Returns whether it was on.
    """
    from django.db import transaction as db_transaction
    from django.utils.translation import get_language

    from ...password_links import _display_name, get_email

    was_on = disable(user)

    if was_on and get_email(user):
        pk, sender, language = user.pk, _display_name(request.user), get_language()
        db_transaction.on_commit(
            lambda: send_reset_mail_task.enqueue(pk, sender, language)
        )

    return was_on


def send_reset_mail(pk, sender, language=None):
    import logging

    from django.contrib.auth import get_user_model
    from django.core.mail import send_mail
    from django.template.loader import render_to_string
    from django.utils import translation
    from django.utils.translation import gettext as _

    from ...password_links import _display_name, get_email
    from ..email_activity.kinds import TWO_FACTOR_RESET, email_kind

    with translation.override(language):
        user = get_user_model()._default_manager.filter(pk=pk).first()

        if user is None or not get_email(user):
            return

        site_title = str(getattr(cs_settings.ADMIN_SITE, "site_title", "") or "")
        context = {
            "name": _display_name(user),
            "sender": sender,
            "site_title": site_title,
        }

        try:
            with email_kind(TWO_FACTOR_RESET):
                send_mail(
                    from_email=None,
                    subject=_("Your two-factor login for %(site)s was reset")
                    % {"site": site_title},
                    message=render_to_string(
                        "content_studio/users/two_factor_reset.txt", context
                    ),
                    recipient_list=[get_email(user)],
                )
        except Exception:
            logging.getLogger("content_studio.users").exception(
                "Could not send the two-factor reset email to user %s", pk
            )


def _make_task():
    from ...password_links import _as_task

    return _as_task(send_reset_mail)


# Workers import tasks by module and function name, so the task keeps the
# name of the function it wraps.
send_reset_mail_task = _make_task()
