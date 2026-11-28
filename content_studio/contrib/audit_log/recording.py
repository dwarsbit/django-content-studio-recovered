"""
What the audit log records besides the activity log: sign-ins, failed
sign-ins and sign-outs, from Django's user_logged_in, user_login_failed
and user_logged_out signals, and the action of each activity log entry.

Only sign-ins through Content Studio are recorded: its login views mark
the request (content_studio.login.mark_sign_in), so a site's own login forms, which send the
same signals, stay out of the log.
"""

import datetime
import logging
import re

from django.contrib.auth import get_user_model
from django.contrib.auth.signals import (
    user_logged_in,
    user_logged_out,
    user_login_failed,
)
from django.core.cache import cache
from django.db import router, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from ...settings import cs_settings
from ...throttling import client_ip

logger = logging.getLogger("content_studio.audit_log")

# The request attribute content_studio.login.mark_sign_in() sets.
MARK = "_content_studio_sign_in"

# How a sign-in was made, when the sender does not say.
PASSWORD = "password"

# Why a sign-in failed, when the sender does not say: Django's
# authenticate() reports a wrong username or password.
WRONG_PASSWORD = "wrong_password"

# Pruning runs at most once an hour, after a sign-in event is written.
PRUNE_CACHE_KEY = "content_studio:audit_log:pruned"
PRUNE_INTERVAL = 3600


def is_marked(request) -> bool:
    request = getattr(request, "_request", request)

    return bool(getattr(request, MARK, False))


def connect():
    user_logged_in.connect(on_logged_in, dispatch_uid="content_studio_audit_log_in")
    user_login_failed.connect(
        on_login_failed, dispatch_uid="content_studio_audit_log_failed"
    )
    user_logged_out.connect(on_logged_out, dispatch_uid="content_studio_audit_log_out")


def on_logged_in(sender, request=None, user=None, **kwargs):
    if request is None or user is None or not is_marked(request):
        return

    record_sign_in(
        "signed_in",
        request,
        user=user,
        method=kwargs.get("method") or PASSWORD,
    )


def on_login_failed(sender, credentials=None, request=None, **kwargs):
    if request is None or not is_marked(request):
        return

    username = str((credentials or {}).get("username") or "")[:255]

    record_sign_in(
        "sign_in_failed",
        request,
        user=find_user(username),
        username=username,
        method=kwargs.get("method") or "",
        reason=kwargs.get("reason") or WRONG_PASSWORD,
    )


def on_logged_out(sender, request=None, user=None, **kwargs):
    if request is None or user is None or not is_marked(request):
        return

    record_sign_in("signed_out", request, user=user)


def find_user(username: str):
    """The user a typed username names, if any."""
    if not username:
        return None

    try:
        return get_user_model()._default_manager.get_by_natural_key(username)
    except Exception:
        return None


def record_sign_in(kind, request, *, user=None, username="", method="", reason=""):
    """
    Write a sign-in event; a failure is logged, never raised, so it
    cannot break a sign-in.
    """
    from .models import SignInEvent

    django_request = getattr(request, "_request", request)

    try:
        if user is not None and not username:
            username = user.get_username()

        # A savepoint: a failed write must not break the transaction of
        # the request it is part of.
        with transaction.atomic(using=router.db_for_write(SignInEvent)):
            SignInEvent.objects.create(
                kind=kind,
                user=user if getattr(user, "pk", None) is not None else None,
                username=str(username or "")[:255],
                method=str(method or "")[:100],
                reason=str(reason or "")[:50],
                ip_address=client_ip(django_request),
                user_agent=str(django_request.META.get("HTTP_USER_AGENT") or "")[:500],
            )
    except Exception:
        logger.exception("Could not record a %s event.", kind)
        return

    maybe_prune()


def record_action(entry, action: str):
    """Keep the action of an activity log entry (see record_change)."""
    from .models import EntryAction

    try:
        with transaction.atomic(using=router.db_for_write(EntryAction)):
            EntryAction.objects.create(log_entry=entry, action=action)
    except Exception:
        logger.exception("Could not record the action of entry %s.", entry.pk)


def prune(now=None) -> tuple[int, int]:
    """
    Delete the activity log entries and sign-in events older than
    AUDIT_LOG_KEEP_DAYS: how many of each. The history versions of the
    pruned entries go with them.
    """
    from django.contrib.admin.models import LogEntry

    from .models import SignInEvent

    days = cs_settings.AUDIT_LOG_KEEP_DAYS

    if days is None:
        return 0, 0

    cutoff = (now or timezone.now()) - datetime.timedelta(days=days)
    entries = LogEntry.objects.filter(action_time__lt=cutoff)
    # Counted first: the delete's total includes cascaded rows.
    entry_count = entries.count()
    entries.delete()
    events, _rows = SignInEvent.objects.filter(created_at__lt=cutoff).delete()

    return entry_count, events


def maybe_prune():
    """Prune, at most once every PRUNE_INTERVAL seconds."""
    if cs_settings.AUDIT_LOG_KEEP_DAYS is None:
        return

    try:
        if cache.add(PRUNE_CACHE_KEY, True, PRUNE_INTERVAL):
            prune()
    except Exception:
        logger.warning("Could not prune the audit log.", exc_info=True)


# Browsers, most specific first: Edge and Opera say Chrome too, Chrome
# says Safari.
BROWSERS = [
    ("Edge", re.compile(r"Edg(?:e|A|iOS)?/")),
    ("Opera", re.compile(r"OPR/|Opera")),
    ("Samsung Internet", re.compile(r"SamsungBrowser/")),
    ("Firefox", re.compile(r"Firefox/|FxiOS/")),
    ("Chrome", re.compile(r"Chrome/|CriOS/")),
    ("Safari", re.compile(r"Safari/")),
]

SYSTEMS = [
    ("iOS", re.compile(r"iPhone|iPad|iPod")),
    ("Android", re.compile(r"Android")),
    ("ChromeOS", re.compile(r"CrOS")),
    ("Windows", re.compile(r"Windows")),
    ("macOS", re.compile(r"Mac OS X|Macintosh")),
    ("Linux", re.compile(r"Linux")),
]


def describe_user_agent(user_agent: str) -> str:
    """A short label for a user agent, such as "Firefox on macOS"."""
    if not user_agent:
        return ""

    browser = next(
        (name for name, pattern in BROWSERS if pattern.search(user_agent)), ""
    )
    system = next((name for name, pattern in SYSTEMS if pattern.search(user_agent)), "")

    if browser and system:
        return _("%(browser)s on %(system)s") % {"browser": browser, "system": system}

    return browser or system or user_agent[:60]
