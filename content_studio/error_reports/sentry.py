"""
Sentry mode: Content Studio's ready() starts the Sentry SDK (the [sentry]
extra) with SENTRY_DSN. Sentry's Django, Huey and logging integrations
enable themselves, so it receives the errors of requests, of the Huey
worker and every line logged at ERROR. Events are tagged with the
request ID and carry no personal data: no user details, cookies or
request bodies.
"""

import logging

from .. import logs
from ..settings import cs_settings
from . import config

logger = logging.getLogger("content_studio.error_reports")

# Headers that are never sent, even if the SDK would.
PRIVATE_HEADERS = {"cookie", "authorization", "x-csrftoken"}


def before_send(event, hint):
    """Tags the event with the request ID and drops cookies and
    credentials from its request."""
    request_id = logs.get_request_id()

    if not request_id:
        record = (hint or {}).get("log_record")
        request_id = getattr(record, "request_id", None)

    if request_id:
        event.setdefault("tags", {})["request_id"] = request_id

    request = event.get("request")

    if isinstance(request, dict):
        request.pop("cookies", None)
        request.pop("data", None)
        headers = request.get("headers")

        if isinstance(headers, dict):
            request["headers"] = {
                name: value
                for name, value in headers.items()
                if name.lower() not in PRIVATE_HEADERS
            }

    return event


def sentry_options() -> dict:
    """The options of sentry_sdk.init."""
    return {
        "dsn": config.get_dsn(),
        "environment": str(cs_settings.SENTRY_ENVIRONMENT or "").strip()
        or "production",
        "release": str(cs_settings.SENTRY_RELEASE or "").strip() or None,
        "traces_sample_rate": config.get_sample_rate(),
        "send_default_pii": False,
        "max_request_body_size": "never",
        "before_send": before_send,
    }


def init_sentry() -> bool:
    """
    Start the Sentry SDK. Returns False when it does not: without
    SENTRY_DSN (a warning), without the SDK or with a bad setting (system
    check E064), or when the project started it itself.
    """
    if not config.get_dsn():
        logger.warning(
            'ERROR_REPORTS is "sentry" but SENTRY_DSN is empty: errors are '
            "only logged."
        )
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.logging import ignore_logger
    except ImportError:
        return False

    try:
        options = sentry_options()
    except (TypeError, ValueError):
        return False

    if sentry_sdk.get_client().is_active():
        return False

    sentry_sdk.init(**options)
    # Requests for a host that is not allowed: bots, never worth an event.
    ignore_logger("django.security.DisallowedHost")
    return True
