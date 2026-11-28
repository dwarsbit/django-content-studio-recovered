"""
System checks of content_studio.contrib.captcha.

- content_studio.E066: a captcha setting that cannot work: CAPTCHA that is
  not True or False, CAPTCHA_CHALLENGES or CAPTCHA_DIFFICULTY outside
  their range, or a CAPTCHA_THROTTLE_RATE that is not a rate or None.
- content_studio.W043: the app is installed but its URLs are not
  included, so the widget has nothing to talk to.
"""

from django.core import checks
from django.urls import NoReverseMatch, reverse

from content_studio.settings import cs_settings
from content_studio.throttling import parse_rate

# Puzzles a challenge may have, and the hex characters a puzzle's target
# may have: each one more multiplies the visitor's work by 16.
CHALLENGES_RANGE = (1, 500)
DIFFICULTY_RANGE = (1, 8)


def _whole_number(value) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def setting_errors() -> list[str]:
    errors = []

    if not isinstance(cs_settings.CAPTCHA, bool):
        errors.append(f"CAPTCHA must be True or False, not {cs_settings.CAPTCHA!r}.")

    for name, (low, high) in (
        ("CAPTCHA_CHALLENGES", CHALLENGES_RANGE),
        ("CAPTCHA_DIFFICULTY", DIFFICULTY_RANGE),
    ):
        value = getattr(cs_settings, name)
        if not _whole_number(value) or not low <= value <= high:
            errors.append(
                f"{name} must be a whole number from {low} to {high}, not {value!r}."
            )

    rate = cs_settings.CAPTCHA_THROTTLE_RATE
    if rate is not None:
        try:
            parse_rate(rate)
        except Exception:
            errors.append(
                f'CAPTCHA_THROTTLE_RATE must be a rate such as "30/minute" or None, not {rate!r}.'
            )

    return errors


@checks.register(checks.Tags.security)
def check_captcha_settings(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    return [
        checks.Error(message, id="content_studio.E066") for message in setting_errors()
    ]


@checks.register(checks.Tags.urls)
def check_captcha_urls(app_configs=None, **kwargs) -> list[checks.CheckMessage]:
    try:
        reverse("content_studio_captcha_challenge")
    except NoReverseMatch:
        return [
            checks.Warning(
                "content_studio.contrib.captcha is installed, but its URLs are not included, "
                "so the captcha widget cannot load a challenge.",
                hint='Add path("api/cap/", include("content_studio.contrib.captcha.urls")) '
                "to your root URLconf, outside the admin.",
                id="content_studio.W043",
            )
        ]
    return []
