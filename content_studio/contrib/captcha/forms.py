"""
The captcha in a Django form, for pages that Django renders:

    from content_studio.contrib.captcha.forms import CaptchaField

    class ContactForm(forms.Form):
        email = forms.EmailField()
        captcha = CaptchaField()

Render ``{{ form.media }}`` on the page: it loads the ``@cap.js/widget``
web component (vendored, version 0.1.58) and points it at this site's
endpoints and solver. The page's Content-Security-Policy must allow
``CAPTCHA_CSP``.
"""

from __future__ import annotations

from typing import Any

from django import forms
from django.urls import reverse
from django.utils.html import format_html
from django.utils.translation import gettext_lazy as _

from content_studio.settings import cs_settings

from .tokens import MAX_TOKEN_LENGTH, verify_captcha

__all__ = ["CAPTCHA_CSP", "CaptchaField", "CaptchaWidget"]

#: The hash of the ``<style>`` the widget adds to its shadow root. It changes
#: with the widget's version; a test recomputes it from the vendored file.
CAPTCHA_STYLE_HASH = "'sha256-wztaw4JykxcHsDODFshiqt3woVAWzD4k5Zi3KJI3B5U='"

#: What a Content-Security-Policy must allow for the widget, by directive:
#: its solver (WebAssembly), its style, its workers (blob URLs) and its
#: icons (data: SVG images).
CAPTCHA_CSP: dict[str, tuple[str, ...]] = {
    "script-src": ("'wasm-unsafe-eval'",),
    "style-src": (CAPTCHA_STYLE_HASH,),
    "worker-src": ("'self'", "blob:"),
    "img-src": ("data:",),
}


def endpoint() -> str:
    """Where the widget talks to the captcha: the path its URLs are included at."""
    challenge = reverse("content_studio_captcha_challenge")
    return challenge.removesuffix("challenge")


class CaptchaWidget(forms.Widget):
    """The ``<cap-widget>`` element; it adds a hidden input with the token to the form."""

    @property
    def media(self) -> forms.Media:
        if not cs_settings.CAPTCHA:
            return forms.Media()
        solver = forms.Script(
            "content_studio/captcha/loader.js",
            defer=True,
            **{"data-solver-url": reverse("content_studio_captcha_solver")},
        )
        return forms.Media(
            js=[solver, forms.Script("content_studio/captcha/cap.min.js", defer=True)]
        )

    def render(
        self,
        name: str,
        value: Any,
        attrs: dict[str, Any] | None = None,
        renderer: Any = None,
    ):
        if not cs_settings.CAPTCHA:
            return ""
        element_id = (attrs or {}).get("id") or self.attrs.get("id") or f"id_{name}"
        return format_html(
            '<cap-widget id="{}" data-cap-api-endpoint="{}" data-cap-hidden-field-name="{}"></cap-widget>',
            element_id,
            endpoint(),
            name,
        )

    def use_required_attribute(self, initial: Any) -> bool:
        return False


class CaptchaField(forms.CharField):
    """A form field for the widget's token. A token is valid once; with the captcha off there is no check."""

    widget = CaptchaWidget
    default_error_messages = {
        "required": _("Verify that you are human."),
        "invalid": _(
            "The captcha is not valid or has expired. Verify that you are human and try again."
        ),
    }

    def __init__(self, **kwargs: Any):
        kwargs.setdefault("max_length", MAX_TOKEN_LENGTH)
        kwargs.setdefault("label", _("Captcha"))
        super().__init__(**kwargs)

    def clean(self, value: Any) -> str:
        if not cs_settings.CAPTCHA:
            return ""
        token = super().clean(value)
        if not verify_captcha(token):
            raise forms.ValidationError(self.error_messages["invalid"], code="invalid")
        return token
