"""
The "Server errors" notification of email mode: with the notifications
app installed, each new error notifies the active superusers. Its key is
the error's signature, so an error that repeats counts up on the unread
notification instead of adding one.
"""

import logging

from django.apps import apps
from django.utils.translation import gettext_lazy as _

EVENT_KEY = "error_reports.server_error"


def notifications_installed() -> bool:
    return apps.is_installed("content_studio.notifications")


def register_error_event() -> None:
    """Make the event known to the notifications app; called from
    Content Studio's ready() in email mode."""
    if not notifications_installed():
        return

    from ..notifications import register_event

    register_event(
        EVENT_KEY,
        label=_("Server errors"),
        description=_(
            "An error on the server, such as a failed request or task. Only "
            "superusers are notified."
        ),
        level="error",
    )


def notify_error(record: logging.LogRecord, text: str, signature: str) -> int:
    """Notify the active superusers of the error; returns how many."""
    if not notifications_installed():
        return 0

    from ..notifications import notify
    from ..notifications.events import get_event
    from .handler import superusers

    try:
        get_event(EVENT_KEY)
    except ValueError:
        # Not registered: error reports are not in email mode.
        return 0

    return notify(
        EVENT_KEY,
        title="%(summary)s",
        body="%(logger)s",
        params={"summary": text, "logger": record.name},
        level="error",
        recipients=superusers(),
        key=signature,
    )
