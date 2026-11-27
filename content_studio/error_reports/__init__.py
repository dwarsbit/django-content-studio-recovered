"""
Error reports: server errors reported to the site's admins, or to
Sentry, while DEBUG is off. Off by default; ERROR_REPORTS turns it on:

- "email": every new error at ERROR or above is mailed to ERROR_EMAIL (or
  the active superusers) and, with the notifications app installed, is a
  "Server errors" notification of the superusers. The same error is
  reported once an hour at most (handler.py).
- "sentry": errors go to Sentry, with the [sentry] extra (sentry.py).
- "off": nothing is reported.
"""

from .handler import ErrorReportHandler

__all__ = [
    "ErrorReportHandler",
]


def set_up() -> None:
    """Called from Content Studio's ready(): register the notification
    event and, while DEBUG is off, start reporting."""
    from django.conf import settings

    from . import config

    mode = config.get_mode()

    if mode == config.EMAIL:
        from .notifying import register_error_event

        register_error_event()

    if settings.DEBUG or config.setting_errors():
        # A bad setting is reported by system check E064.
        return

    if mode == config.EMAIL:
        from .handler import install_handler

        install_handler()
    elif mode == config.SENTRY:
        from .sentry import init_sentry

        init_sentry()
