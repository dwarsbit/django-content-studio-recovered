"""
A self-hosted captcha: the Cap protocol (https://capjs.js.org), a proof
of work the visitor's browser solves, with no third party and no
tracking.

Add ``"content_studio.contrib.captcha"`` to ``INSTALLED_APPS`` and include
its URLs outside the admin:

    urlpatterns = [
        path("api/cap/", include("content_studio.contrib.captcha.urls")),
        path("admin/", include("content_studio.urls")),
    ]

Then:

- ``content_studio.contrib.captcha.forms.CaptchaField`` puts the widget in
  a Django form and checks its token;
- ``content_studio.contrib.captcha.fields.CaptchaField`` checks a token in
  a Django REST Framework serializer;
- ``verify_captcha(token)`` checks one anywhere else;
- ``content_studio.contrib.captcha.dashboard.CaptchaStatisticWidget``
  shows the solved and failed challenges on the dashboard.

A token is valid once. ``CONTENT_STUDIO["CAPTCHA"] = False`` turns the
check off.
"""

from .tokens import verify_captcha

__all__ = ["verify_captcha"]
