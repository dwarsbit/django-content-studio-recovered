"""
What an email is, for the Email activity page: set around the sending
code with email_kind(), or with the X-Content-Studio-Kind header.

Importable whether or not the app is installed, so Content Studio's own
emails can carry their kind either way.
"""

import contextlib
import contextvars

from django.utils.translation import gettext_lazy as _

# The header an app may set instead of email_kind(); the logging backend
# removes it before the email is delivered.
KIND_HEADER = "X-Content-Studio-Kind"

INVITE = "invite"
PASSWORD_LINK = "password_link"
PASSWORD_RESET = "password_reset"
TWO_FACTOR_RESET = "two_factor_reset"
EMAIL_CHANGED = "email_changed"
NOTIFICATION_DIGEST = "notification_digest"
TEST = "test"

# Content Studio's own kinds; other kinds are shown as they are written.
LABELS = {
    INVITE: _("Invite"),
    PASSWORD_LINK: _("Password link"),
    PASSWORD_RESET: _("Password reset"),
    TWO_FACTOR_RESET: _("Two-factor reset"),
    EMAIL_CHANGED: _("Email address changed"),
    NOTIFICATION_DIGEST: _("Notification digest"),
    TEST: _("Test email"),
}

# The kind of the emails sent in this context, and who sent them.
_kind: contextvars.ContextVar[str] = contextvars.ContextVar(
    "content_studio_email_kind", default=""
)
_sender: contextvars.ContextVar[object | None] = contextvars.ContextVar(
    "content_studio_email_sender", default=None
)


@contextlib.contextmanager
def email_kind(kind: str, sent_by=None):
    """
    Log the emails sent inside the block with this kind (a short name
    such as "order_confirmation"), and optionally the user who sent them.
    """
    kind_token = _kind.set(str(kind or "")[:50])
    sender_token = _sender.set(sent_by)

    try:
        yield
    finally:
        _kind.reset(kind_token)
        _sender.reset(sender_token)


def current_kind() -> str:
    return _kind.get()


def current_sender():
    return _sender.get()


def kind_label(kind: str) -> str:
    """The kind as the page shows it."""
    if not kind:
        return str(_("Other"))

    label = LABELS.get(kind)

    if label is not None:
        return str(label)

    return kind.replace("_", " ").replace("-", " ").capitalize()
