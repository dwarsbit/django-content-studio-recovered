"""
Error reports on the system status page (content_studio.contrib.status):
the Error reports row of the services, and the Recent errors card.
"""

from django.conf import settings
from django.utils.translation import gettext_lazy as _
from django.utils.translation import ngettext

from ..settings import cs_settings
from . import config

# Error notifications the Recent errors card shows.
RECENT_ERRORS = 8


def check_error_reports():
    """The Error reports row: where errors go, and whether they get there."""
    from ..contrib.status.registry import degraded, down, ok, unknown

    mode = config.get_mode()

    if mode not in config.MODES:
        return down(str(cs_settings.ERROR_REPORTS), _("Unknown mode."))

    if mode == config.SENTRY:
        if not config.sentry_installed():
            return down(_("Sentry"), _("The Sentry SDK is not installed."))

        if not config.get_dsn():
            return down(_("Sentry"), _("SENTRY_DSN is empty."))

        detail = _("Sentry")
        environment = str(cs_settings.SENTRY_ENVIRONMENT or "").strip()

        if environment:
            detail = f"{detail} · {environment}"
    else:
        from .handler import recipients

        count = len(recipients())

        if count == 0:
            return degraded(
                _("Email"),
                _(
                    "Nobody gets the emails: set ERROR_EMAIL or give a superuser "
                    "an email address."
                ),
            )

        detail = ngettext(
            "Email to %(count)s recipient", "Email to %(count)s recipients", count
        ) % {"count": count}

    if settings.DEBUG:
        return unknown(detail, _("Nothing is reported while DEBUG is on."))

    return ok(detail)


def register_status() -> None:
    """Add the Error reports row unless error reports are off."""
    from ..contrib.status.builtin import GROUP
    from ..contrib.status.registry import register_service

    if config.get_mode() == config.OFF:
        return

    register_service(
        "content_studio.error_reports",
        _("Error reports"),
        check_error_reports,
        icon="ph-bold ph-bug",
        group=GROUP,
    )


def recent_errors_enabled() -> bool:
    """The card is shown in email mode with the notifications app."""
    from .notifying import notifications_installed

    return config.get_mode() == config.EMAIL and notifications_installed()


def get_recent_errors(request) -> dict:
    """The viewer's latest error notifications, newest first."""
    if not recent_errors_enabled():
        return {"enabled": False, "errors": []}

    from ..notifications.reading import visible_notifications
    from .notifying import EVENT_KEY

    notifications = visible_notifications(request).filter(event=EVENT_KEY)[
        :RECENT_ERRORS
    ]

    return {
        "enabled": True,
        "errors": [
            {
                "id": notification.pk,
                "title": notification.get_title()[:200] or str(_("Error")),
                "logger": notification.get_body(),
                "count": notification.count,
                "first_seen": notification.created_at.isoformat(),
                "last_seen": notification.updated_at.isoformat(),
                "read": notification.read_at is not None,
            }
            for notification in notifications
        ],
    }
