"""
The languages of the admin.

Content Studio picks the editor's language itself, for its own URLs, so
the menus (the frontend) and the labels, choices and errors (Django)
always speak the same language, with or without LocaleMiddleware in the
project. The order: the language cookie (set by the language picker in
the user menu, Django's LANGUAGE_COOKIE_NAME), the browser's
Accept-Language, then LANGUAGE_CODE. Only the languages Content Studio
ships and the project's LANGUAGES setting allows are picked; otherwise
the admin falls back to English.
"""

from functools import wraps

from django.conf import settings
from django.utils import translation
from django.utils.translation.trans_real import parse_accept_lang_header

# The languages Content Studio ships, by Django language code, with each
# language's own name (shown by the language picker). Every one has a
# frontend locale (frontend/public/locales/<locale>/translation.json) and
# a Django catalog (locale/<locale>/LC_MESSAGES/django.po); the tests
# keep the three in step.
LANGUAGES = {
    "en": "English",
    "de": "Deutsch",
    "es": "Español",
    "fr": "Français",
    "it": "Italiano",
    "nl": "Nederlands",
    "pt-br": "Português (Brasil)",
}

FALLBACK_LANGUAGE = "en"


def get_locale(language: str) -> str:
    """The frontend locale of a language code: pt-br is pt-BR."""
    return translation.to_locale(language).replace("_", "-")


def get_enabled_languages() -> list[str]:
    """
    The languages an editor can pick: the shipped ones the project's
    LANGUAGES allows, by code ("pt-br"), its generic code ("pt") or a
    regional variant ("de-at" allows "de"). English when none is.
    """

    allowed = {code.lower() for code, _name in settings.LANGUAGES}
    enabled = []

    for code in LANGUAGES:
        generic = code.split("-")[0]

        if (
            code in allowed
            or generic in allowed
            or any(other.split("-")[0] == generic for other in allowed)
        ):
            enabled.append(code)

    return enabled or [FALLBACK_LANGUAGE]


def match_language(code: str | None, enabled: list[str]) -> str | None:
    """
    The enabled language for a language code: the code itself, its
    generic language ("de-at" is "de") or a regional one ("pt" is
    "pt-br"). None when nothing matches.
    """

    if not code:
        return None

    code = code.lower().replace("_", "-")

    if code in enabled:
        return code

    generic = code.split("-")[0]

    if generic in enabled:
        return generic

    for language in enabled:
        if language.split("-")[0] == generic:
            return language

    return None


def get_admin_language(request) -> str:
    """The language of the admin for this request (see the module)."""

    enabled = get_enabled_languages()
    language = match_language(
        request.COOKIES.get(settings.LANGUAGE_COOKIE_NAME), enabled
    )

    if language:
        return language

    for accepted, _quality in parse_accept_lang_header(
        request.META.get("HTTP_ACCEPT_LANGUAGE", "")
    ):
        if accepted == "*":
            break

        language = match_language(accepted, enabled)

        if language:
            return language

    return (
        match_language(settings.LANGUAGE_CODE, enabled)
        or match_language(FALLBACK_LANGUAGE, enabled)
        or enabled[0]
    )


def _in_language(language, iterator):
    # A streamed response (the CSV export) renders after the view
    # returned: its rows are made in the admin's language too.
    with translation.override(language):
        yield from iterator


def admin_language(view):
    """
    Runs a view in the admin's language. The response renders inside it
    (a DRF Response renders after the view otherwise, and lazy strings
    such as verbose names would come out in the project's language).
    """

    @wraps(view)
    def wrapped(request, *args, **kwargs):
        language = get_admin_language(request)
        request.LANGUAGE_CODE = language

        with translation.override(language):
            response = view(request, *args, **kwargs)
            render = getattr(response, "render", None)

            if callable(render) and not getattr(response, "is_rendered", True):
                response = render() or response

        if getattr(response, "streaming", False):
            response.streaming_content = _in_language(
                language, response.streaming_content
            )

        if not response.has_header("Content-Language"):
            response["Content-Language"] = language

        return response

    return wrapped


def in_admin_language(urlpatterns):
    """Wraps every view of these URL patterns with admin_language."""

    for pattern in urlpatterns:
        if hasattr(pattern, "url_patterns"):
            in_admin_language(pattern.url_patterns)
        else:
            pattern.callback = admin_language(pattern.callback)

    return urlpatterns
