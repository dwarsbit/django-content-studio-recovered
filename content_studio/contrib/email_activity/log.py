"""
Writing sent emails to the log, and reading it back: masking, pruning
and the counts the page and the status page show.
"""

import datetime
import logging
from email.utils import parseaddr

from django.core.cache import cache
from django.db import router, transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from ...settings import cs_settings

logger = logging.getLogger("content_studio.email_activity")

SMTP_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
LOGGING_BACKEND = "content_studio.contrib.email_activity.backends.EmailBackend"

# Email backends that send nothing.
LOCAL_BACKENDS = {
    "django.core.mail.backends.console.EmailBackend": "Console",
    "django.core.mail.backends.locmem.EmailBackend": "Local memory",
    "django.core.mail.backends.filebased.EmailBackend": "Files",
    "django.core.mail.backends.dummy.EmailBackend": "Dummy",
}

# The longest subject kept: the most a header line may hold.
MAX_SUBJECT = 998

# Old emails are pruned at most this often, after a send.
PRUNE_INTERVAL = 3600
PRUNE_CACHE_KEY = "content_studio:email_activity:pruned"


def backend_path(backend) -> str:
    cls = backend if isinstance(backend, type) else type(backend)
    return f"{cls.__module__}.{cls.__qualname__}"


def describe_backend(backend) -> str:
    """A backend as the page shows it: "SMTP · smtp.example.com:587"."""
    from django.core.mail.backends.smtp import EmailBackend as SMTPBackend

    if isinstance(backend, SMTPBackend):
        return f"SMTP · {backend.host}:{backend.port}"

    path = backend_path(backend)

    if path in LOCAL_BACKENDS:
        return LOCAL_BACKENDS[path]

    module, _dot, name = path.rpartition(".")
    return module if name == "EmailBackend" else path


def default_backend_path() -> str:
    """The backend Django sends with by default, as a dotted path."""
    import warnings

    from django.conf import settings

    with warnings.catch_warnings():
        # Django 6.1 deprecates EMAIL_BACKEND for MAILERS.
        warnings.simplefilter("ignore")
        mailers = getattr(settings, "MAILERS", None)

        if mailers is not None:
            return (mailers.get("default") or {}).get("BACKEND", SMTP_BACKEND)

        return settings.EMAIL_BACKEND


def is_logging() -> bool:
    """Whether the emails the site sends by default end up in the log."""
    from django.utils.module_loading import import_string

    from .backends import EmailBackend

    try:
        backend = import_string(default_backend_path())
    except ImportError:
        return False

    return isinstance(backend, type) and issubclass(backend, EmailBackend)


def mask_address(address: str) -> str:
    """s***@example.com for "Sam Lee <sam@example.com>"."""
    _name, email = parseaddr(str(address))

    if "@" not in email:
        return "***"

    local, _at, domain = email.rpartition("@")
    return f"{local[:1]}***@{domain}"


def addresses(values) -> list[str]:
    values = [str(value) for value in values or []]

    if cs_settings.EMAIL_ACTIVITY_MASK:
        return [mask_address(value) for value in values]

    return values


def describe_error(exc: BaseException) -> str:
    return f"{type(exc).__name__}: {exc}".rstrip(": ")


def describe_attachments(message) -> list[dict]:
    """Each attachment's name, type and size; never its content."""
    found = []

    for attachment in getattr(message, "attachments", None) or []:
        try:
            if hasattr(attachment, "get_content_type"):
                payload = attachment.get_payload(decode=True) or b""
                found.append(
                    {
                        "name": attachment.get_filename() or "",
                        "type": attachment.get_content_type(),
                        "size": len(payload),
                    }
                )
                continue

            name, content, mimetype = tuple(attachment)[:3]

            if isinstance(content, str):
                content = content.encode()

            found.append(
                {
                    "name": name or "",
                    "type": mimetype or "",
                    "size": len(content or b""),
                }
            )
        except Exception:
            found.append({"name": "", "type": "", "size": None})

    return found


def message_size(message) -> int | None:
    try:
        return len(message.message().as_bytes())
    except Exception:
        return None


def record(
    message,
    *,
    status: str,
    error: str = "",
    backend: str = "",
    kind: str = "",
    sent_by=None,
    created_at: datetime.datetime,
    duration: float | None = None,
    message_id: str = "",
    size: int | None = None,
):
    """
    Log one email. Never raises: a log that cannot be written must not
    keep an email from being sent.
    """
    from .models import SentEmail

    try:
        masked = cs_settings.EMAIL_ACTIVITY_MASK
        to = addresses(getattr(message, "to", None))
        cc = addresses(getattr(message, "cc", None))
        bcc = addresses(getattr(message, "bcc", None))
        reply_to = addresses(getattr(message, "reply_to", None))
        subject = "" if masked else str(getattr(message, "subject", "") or "")
        user = sent_by if getattr(sent_by, "pk", None) is not None else None
        using = router.db_for_write(SentEmail)

        # A savepoint: a failed write must not break the caller's transaction.
        with transaction.atomic(using=using):
            entry = SentEmail.objects.using(using).create(
                from_email=str(getattr(message, "from_email", "") or "")[:500],
                to=to,
                cc=cc,
                bcc=bcc,
                reply_to=reply_to,
                recipients=", ".join([*to, *cc, *bcc]),
                subject=subject[:MAX_SUBJECT],
                kind=kind[:50],
                status=status,
                error=error,
                backend=backend[:200],
                message_id=message_id[:255],
                attachments=describe_attachments(message),
                size=size,
                sent_by=user,
                created_at=created_at,
                finished_at=timezone.now(),
                duration=None if duration is None else max(round(duration * 1000), 0),
            )
    except Exception:
        logger.exception("Could not log the email %r.", getattr(message, "subject", ""))
        return None

    maybe_prune()
    return entry


def prune(now=None) -> int:
    """Delete the emails older than EMAIL_ACTIVITY_KEEP_DAYS; how many."""
    from .models import SentEmail

    days = cs_settings.EMAIL_ACTIVITY_KEEP_DAYS

    if days is None:
        return 0

    cutoff = (now or timezone.now()) - datetime.timedelta(days=days)
    deleted, _rows = SentEmail.objects.filter(created_at__lt=cutoff).delete()
    return deleted


def maybe_prune():
    """Prune, at most once every PRUNE_INTERVAL seconds."""
    try:
        if cache.add(PRUNE_CACHE_KEY, True, PRUNE_INTERVAL):
            prune()
    except Exception:
        logger.warning("Could not prune the email log.", exc_info=True)


def recent_counts(hours: int = 24) -> tuple[int, int]:
    """Emails sent and failed in the last hours."""
    from django.db.models import Count, Q

    from .models import SentEmail

    since = timezone.now() - datetime.timedelta(hours=hours)
    counts = SentEmail.objects.filter(created_at__gte=since).aggregate(
        sent=Count("pk", filter=Q(status=SentEmail.SENT)),
        failed=Count("pk", filter=Q(status=SentEmail.FAILED)),
    )
    return counts["sent"], counts["failed"]


def status_summary() -> tuple[str, str]:
    """
    For the Email row on the status page: a detail like "42 sent in 24
    hours", and a message when emails failed in that time.
    """
    sent, failed = recent_counts()
    detail = _("%(count)s sent in 24 hours") % {"count": sent}

    if not failed:
        return detail, ""

    return detail, _("%(failed)s of %(total)s emails failed in the last 24 hours.") % {
        "failed": failed,
        "total": sent + failed,
    }


def default_connection():
    """The connection Django sends with by default."""
    import warnings

    from django.core import mail

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        mailers = getattr(mail, "mailers", None)

        if mailers is not None:
            # Django 6.1 and later: MAILERS, or the settings it replaces.
            return mailers.default

        return mail.get_connection()


def delivery_description() -> str:
    """How emails leave the site, as the page shows it."""
    from .backends import EmailBackend

    try:
        connection = default_connection()

        if isinstance(connection, EmailBackend):
            connection = connection.delivery

        return describe_backend(connection)
    except Exception as exc:
        return describe_error(exc)
