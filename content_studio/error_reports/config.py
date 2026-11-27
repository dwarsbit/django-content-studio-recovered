"""
Reading the error report settings. Each accepts the plain string an
environment variable gives, so a project can pass os.environ values
straight through.
"""

from django.conf import settings
from django.core.validators import validate_email
from django.core.exceptions import ValidationError

from ..settings import cs_settings

EMAIL = "email"
SENTRY = "sentry"
OFF = "off"
MODES = (EMAIL, SENTRY, OFF)


def get_mode() -> str:
    """ERROR_REPORTS lowercased: "email", "sentry", "off", or the wrong
    value as given (reported by system check E064). Empty is "off"."""
    value = cs_settings.ERROR_REPORTS

    if value is None:
        return OFF

    mode = str(value).strip().lower()
    return mode or OFF


def is_active() -> bool:
    """Whether errors are reported: a known mode other than off, with
    DEBUG off."""
    return not settings.DEBUG and get_mode() in (EMAIL, SENTRY)


def get_error_email() -> list[str]:
    """ERROR_EMAIL as a list: a list or tuple, or a comma-separated
    string."""
    value = cs_settings.ERROR_EMAIL

    if not value:
        return []

    if isinstance(value, str):
        value = value.split(",")

    if not isinstance(value, (list, tuple)):
        return []

    return [str(address).strip() for address in value if str(address).strip()]


def get_sample_rate() -> float:
    """SENTRY_TRACES_SAMPLE_RATE as a float; ValueError when it is not a
    number from 0 to 1."""
    value = cs_settings.SENTRY_TRACES_SAMPLE_RATE

    if value is None or value == "":
        return 0.0

    if isinstance(value, bool):
        raise ValueError(value)

    rate = float(value)

    if not 0 <= rate <= 1:
        raise ValueError(value)

    return rate


def get_dsn() -> str:
    return str(cs_settings.SENTRY_DSN or "").strip()


def sentry_installed() -> bool:
    try:
        import sentry_sdk  # noqa: F401
    except ImportError:
        return False

    return True


def setting_errors() -> list[str]:
    """Error report settings that cannot work (system check E064)."""
    errors = []
    mode = get_mode()

    if mode not in MODES:
        errors.append(
            f'ERROR_REPORTS must be "email", "sentry" or "off", not '
            f"{cs_settings.ERROR_REPORTS!r}."
        )

    value = cs_settings.ERROR_EMAIL

    if value and not isinstance(value, (str, list, tuple)):
        errors.append(
            "ERROR_EMAIL must be a list of email addresses or a comma-separated "
            f"string, not {value!r}."
        )
    else:
        for address in get_error_email():
            try:
                validate_email(address)
            except ValidationError:
                errors.append(f"ERROR_EMAIL has an invalid address: {address!r}.")

    try:
        get_sample_rate()
    except (TypeError, ValueError):
        errors.append(
            "SENTRY_TRACES_SAMPLE_RATE must be a number from 0 to 1, not "
            f"{cs_settings.SENTRY_TRACES_SAMPLE_RATE!r}."
        )

    if mode == SENTRY and not sentry_installed():
        errors.append(
            'ERROR_REPORTS is "sentry" but the Sentry SDK is not installed: '
            'install "django-content-studio[sentry]".'
        )

    return errors
