"""
The logging email backend: it records each email in the Email activity
log and hands it to the backend that delivers it, EMAIL_DELIVERY_BACKEND
(Django's SMTP backend by default).

    EMAIL_BACKEND = "content_studio.contrib.email_activity.backends.EmailBackend"

With Django's MAILERS (6.1 and later), use it as a mailer's BACKEND; its
OPTIONS go to the delivering backend.
"""

import time

from django.core.exceptions import ImproperlyConfigured
from django.core.mail.backends.base import BaseEmailBackend
from django.utils import timezone
from django.utils.module_loading import import_string
from django.utils.translation import gettext as _

from ...settings import cs_settings
from . import log
from .kinds import KIND_HEADER, current_kind, current_sender

# SentEmail's statuses; the model is imported only to write the log.
SENT = "sent"
FAILED = "failed"


def get_delivery_backend_class():
    path = cs_settings.EMAIL_DELIVERY_BACKEND or log.SMTP_BACKEND

    try:
        backend = import_string(path)
    except ImportError as exc:
        raise ImproperlyConfigured(
            f"EMAIL_DELIVERY_BACKEND {path!r} could not be imported: {exc}"
        ) from exc

    if isinstance(backend, type) and issubclass(backend, EmailBackend):
        raise ImproperlyConfigured(
            "EMAIL_DELIVERY_BACKEND is the logging backend itself. Set it to the "
            "backend that delivers the emails, such as Django's SMTP backend."
        )

    return backend


def pop_kind(message) -> str:
    """The kind header's value, removed from the email."""
    headers = getattr(message, "extra_headers", None)

    if not headers:
        return ""

    for name in list(headers):
        if name.lower() == KIND_HEADER.lower():
            return str(headers.pop(name) or "")

    return ""


def pin_message_id(message) -> str:
    """
    Give the email its Message-ID now, so the log holds the one that is
    sent (Django otherwise makes a new one each time it builds it).
    """
    from email.utils import make_msgid

    from django.core.mail.utils import DNS_NAME

    headers = getattr(message, "extra_headers", None)

    if headers is None:
        return ""

    for name, value in headers.items():
        if name.lower() == "message-id":
            return str(value)

    headers["Message-ID"] = make_msgid(domain=DNS_NAME)
    return headers["Message-ID"]


class EmailBackend(BaseEmailBackend):
    """Logs every email, then delivers it with EMAIL_DELIVERY_BACKEND."""

    def __init__(self, *args, **kwargs):
        # Not BaseEmailBackend.__init__(): every option but fail_silently
        # belongs to the delivering backend.
        if args:
            fail_silently, args = args[0], args[1:]
        else:
            fail_silently = kwargs.pop("fail_silently", False)

        self.fail_silently = bool(fail_silently)
        self.alias = kwargs.get("alias")
        # Always raising, so the log holds the reason; fail_silently is
        # applied here.
        self.delivery = get_delivery_backend_class()(*args, **kwargs)

    def open(self):
        return self.delivery.open()

    def close(self):
        return self.delivery.close()

    def send_messages(self, email_messages):
        messages = list(email_messages or [])

        if not messages:
            return 0

        backend = log.describe_backend(self.delivery)
        sent_by = current_sender()
        default_kind = current_kind()
        prepared = []

        for message in messages:
            kind = pop_kind(message) or default_kind
            message_id = pin_message_id(message)
            prepared.append((message, kind, message_id, log.message_size(message)))

        def record(entry, status, error="", started=None, began=None):
            message, kind, message_id, size = entry
            log.record(
                message,
                status=status,
                error=error,
                backend=backend,
                kind=kind,
                sent_by=sent_by,
                created_at=started or timezone.now(),
                duration=None if began is None else time.monotonic() - began,
                message_id=message_id,
                size=size,
            )

        try:
            new_connection = self.delivery.open()
        except Exception as exc:
            for entry in prepared:
                record(entry, FAILED, log.describe_error(exc))

            if self.fail_silently:
                return 0
            raise

        sent = 0

        try:
            for entry in prepared:
                started, began = timezone.now(), time.monotonic()

                try:
                    count = self.delivery.send_messages([entry[0]]) or 0
                except Exception as exc:
                    record(entry, FAILED, log.describe_error(exc), started, began)

                    if self.fail_silently:
                        continue
                    raise

                if count:
                    record(entry, SENT, "", started, began)
                    sent += count
                else:
                    record(
                        entry,
                        FAILED,
                        _("The email backend did not send it."),
                        started,
                        began,
                    )
        finally:
            if new_connection:
                try:
                    self.delivery.close()
                except Exception:
                    if not self.fail_silently:
                        raise

        return sent
