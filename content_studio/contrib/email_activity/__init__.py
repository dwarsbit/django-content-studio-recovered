"""
Email activity: a log of every email the site sends (who it was from and
to, the subject, whether it was sent and the error when it was not),
shown on a page linked from the system status page, with a button to
send a test email. Bodies and attachment contents are never stored.

Add "content_studio.contrib.email_activity" to INSTALLED_APPS and put
the logging backend in front of the backend that delivers:

    EMAIL_BACKEND = "content_studio.contrib.email_activity.backends.EmailBackend"

    CONTENT_STUDIO = {
        # Only when you don't deliver over SMTP (the default):
        "EMAIL_DELIVERY_BACKEND": "anymail.backends.postmark.EmailBackend",
    }

Give the emails your app sends a kind, shown and filtered on the page:

    from content_studio.contrib.email_activity import email_kind

    with email_kind("order_confirmation"):
        send_mail(...)

or set the X-Content-Studio-Kind header on an EmailMessage; the logging
backend removes it before the email is delivered.
"""

from .kinds import KIND_HEADER, email_kind

__all__ = ["KIND_HEADER", "email_kind"]
