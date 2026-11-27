"""
Email mode: a logging handler that reports every new error by email and,
with the notifications app installed, as a "Server errors" notification
of the superusers.

Every record at ERROR or above counts: a server error (500), a failed
task, anything logged as an error. Records with the same signature (the
logger, the exception type and where it was raised) are reported once an
hour at most; the notification of an error that repeats counts up
instead of adding a line.
"""

from __future__ import annotations

import hashlib
import logging
import threading
import traceback

from .. import logs
from . import config

logger = logging.getLogger("content_studio.error_reports")

# Seconds before the same error is reported again.
REPEAT_SECONDS = 60 * 60
CACHE_PREFIX = "content_studio:error:"

# Loggers never reported: requests for a host that is not allowed come
# from bots, and the reports' own warnings would loop.
IGNORED_LOGGERS = ("django.security.DisallowedHost", logger.name)

_local = threading.local()


def signature(record: logging.LogRecord) -> str:
    """The same error gives the same signature: the logger, the exception
    type and the file:line it was raised at; without an exception, the
    logger and the message before it was filled in."""
    parts = [record.name]

    if record.exc_info and record.exc_info[0]:
        kind, _, tb = record.exc_info
        parts.append(kind.__qualname__)
        frames = traceback.extract_tb(tb)

        if frames:
            parts.append(f"{frames[-1].filename}:{frames[-1].lineno}")
    else:
        parts.append(str(record.msg))

    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:20]


def summary(record: logging.LogRecord) -> str:
    """The first line of the message (or of the exception), at most 150
    characters."""
    message = record.getMessage()
    message = message.splitlines()[0].strip() if message.strip() else ""

    if not message and record.exc_info and record.exc_info[1] is not None:
        error = record.exc_info[1]
        lines = f"{type(error).__name__}: {error}".splitlines()
        message = lines[0] if lines else type(error).__name__

    return message[:150]


def request_id(record: logging.LogRecord) -> str | None:
    """The request ID: set on the record by RequestIdFilter, kept by
    RequestIdMiddleware, or on the record's request."""
    found = getattr(record, "request_id", None) or logs.get_request_id()

    if not found:
        request = getattr(record, "request", None)
        found = getattr(request, "request_id", None)

    return str(found) if found else None


def superusers():
    from django.contrib.auth import get_user_model

    return get_user_model()._default_manager.filter(is_superuser=True, is_active=True)


def recipients() -> list[str]:
    """ERROR_EMAIL, or the active superusers' email addresses."""
    configured = config.get_error_email()

    if configured:
        return configured

    from django.contrib.auth import get_user_model

    field = get_user_model().get_email_field_name()
    return sorted(
        {email for email in superusers().values_list(field, flat=True) if email}
    )


def project_name() -> str:
    from ..settings import cs_settings

    return str(getattr(cs_settings.ADMIN_SITE, "site_title", "") or "Django")


def send_report(record: logging.LogRecord, formatted: str) -> None:
    """Mail the error and notify the superusers about it."""
    from django.core.mail import send_mail

    from ..contrib.email_activity.kinds import ERROR_REPORT, email_kind
    from .notifying import notify_error

    text = summary(record)
    rid = request_id(record)
    to = recipients()

    if to:
        body = f"{formatted}\n\nLogger: {record.name}\n"

        if rid:
            body += f"Request ID: {rid}\n"

        with email_kind(ERROR_REPORT):
            send_mail(f"[{project_name()}] {record.levelname}: {text}", body, None, to)

    notify_error(record, text, signature(record))


class ErrorReportHandler(logging.Handler):
    """
    Reports each new error by email and as an admin notification, once an
    hour at most (see the module). It never raises: a report that fails
    is logged as a warning on content_studio.error_reports.
    """

    def __init__(self, level=logging.ERROR):
        super().__init__(level)

    def emit(self, record: logging.LogRecord) -> None:
        if getattr(_local, "busy", False) or record.name.startswith(IGNORED_LOGGERS):
            return

        _local.busy = True

        try:
            from django.core.cache import cache

            if not cache.add(f"{CACHE_PREFIX}{signature(record)}", 1, REPEAT_SECONDS):
                return

            send_report(record, self.format(record))
        except Exception:  # a report must never break the request
            logger.warning("Could not report an error", exc_info=True)
        finally:
            _local.busy = False


def _has_handler(log: logging.Logger) -> bool:
    return any(isinstance(handler, ErrorReportHandler) for handler in log.handlers)


def install_handler() -> list[str]:
    """
    Add the handler to the root logger and to every configured logger
    that keeps its records to itself (propagate off, with handlers of its
    own, like "django" and "huey" in logging_settings()), so every error
    reaches it once. A project whose LOGGING already names the handler
    keeps its own setup. Returns the names of the loggers it was added to.
    """
    loggers = [
        log
        for name, log in logging.root.manager.loggerDict.items()
        if isinstance(log, logging.Logger)
    ]

    if _has_handler(logging.root) or any(_has_handler(log) for log in loggers):
        return []

    handler = ErrorReportHandler()
    logging.root.addHandler(handler)
    added = ["root"]

    for log in loggers:
        if log.propagate or not log.handlers:
            continue

        if log.name.startswith(IGNORED_LOGGERS):
            continue

        log.addHandler(handler)
        added.append(log.name)

    return added


def uninstall_handler() -> None:
    """Remove the handler from every logger (for tests)."""
    for log in [logging.root, *logging.root.manager.loggerDict.values()]:
        if not isinstance(log, logging.Logger):
            continue

        for handler in list(log.handlers):
            if isinstance(handler, ErrorReportHandler):
                log.removeHandler(handler)
