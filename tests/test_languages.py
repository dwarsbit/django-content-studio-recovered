"""
Tests for the admin's languages: which language a request gets, the
language picker's endpoint, the page Django renders for the frontend, and
the catalogs (every shipped language has every string of the frontend and
of Django).
"""

import gettext
import json
import re
from pathlib import Path

from django.contrib.auth import models as auth_models
from django.test import RequestFactory, SimpleTestCase, TestCase, override_settings
from django.utils.translation import to_locale
from rest_framework.test import APIClient

from content_studio.languages import (
    LANGUAGES,
    get_admin_language,
    get_enabled_languages,
    get_locale,
    match_language,
)
from content_studio.token_backends.jwt import create_access_token

ROOT = Path(__file__).resolve().parent.parent
FRONTEND_LOCALES = ROOT / "frontend" / "public" / "locales"
DJANGO_LOCALES = ROOT / "content_studio" / "locale"

# The plural forms i18next asks for in each language (Intl.PluralRules'
# categories). A new language needs its entry here.
PLURAL_CATEGORIES = {
    "en": {"one", "other"},
    "de": {"one", "other"},
    "es": {"one", "many", "other"},
    "fr": {"one", "many", "other"},
    "it": {"one", "many", "other"},
    "nl": {"one", "other"},
    "pt-br": {"one", "many", "other"},
}

PLURAL_SUFFIX = re.compile(r"_(zero|one|two|few|many|other)$")
FRONTEND_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*(?:,[^}]*)?\}\}")
DJANGO_PLACEHOLDER = re.compile(r"%(?:\((\w+)\))?[sd]")


def flatten(data, prefix=""):
    for key, value in data.items():
        if isinstance(value, dict):
            yield from flatten(value, f"{prefix}{key}.")
        else:
            yield f"{prefix}{key}", value


def frontend_strings(language):
    path = FRONTEND_LOCALES / get_locale(language) / "translation.json"
    return dict(flatten(json.loads(path.read_text())))


def request(cookie=None, accept=None):
    factory = RequestFactory()
    headers = {}

    if accept:
        headers["HTTP_ACCEPT_LANGUAGE"] = accept

    req = factory.get("/", **headers)

    if cookie:
        req.COOKIES["django_language"] = cookie

    return req


class EnabledLanguagesTests(SimpleTestCase):
    def test_every_shipped_language_with_djangos_default_languages(self):
        self.assertEqual(get_enabled_languages(), list(LANGUAGES))

    @override_settings(LANGUAGES=[("en", "English"), ("nl", "Dutch")])
    def test_the_projects_languages_limit_them(self):
        self.assertEqual(get_enabled_languages(), ["en", "nl"])

    @override_settings(LANGUAGES=[("pt", "Portuguese"), ("de-at", "Austrian")])
    def test_generic_and_regional_codes_match(self):
        self.assertEqual(get_enabled_languages(), ["de", "pt-br"])

    @override_settings(LANGUAGES=[("ja", "Japanese")])
    def test_english_when_none_is_shipped(self):
        self.assertEqual(get_enabled_languages(), ["en"])

    def test_match_language(self):
        enabled = ["en", "de", "pt-br"]

        self.assertEqual(match_language("de", enabled), "de")
        self.assertEqual(match_language("de-CH", enabled), "de")
        self.assertEqual(match_language("pt", enabled), "pt-br")
        self.assertEqual(match_language("pt_BR", enabled), "pt-br")
        self.assertIsNone(match_language("ja", enabled))
        self.assertIsNone(match_language("", enabled))

    def test_frontend_locales(self):
        self.assertEqual(get_locale("pt-br"), "pt-BR")
        self.assertEqual(get_locale("de"), "de")


class AdminLanguageTests(SimpleTestCase):
    def test_the_cookie_comes_first(self):
        self.assertEqual(get_admin_language(request("fr", "de,en;q=0.5")), "fr")

    def test_then_the_browser(self):
        self.assertEqual(get_admin_language(request(accept="ja,de;q=0.8")), "de")
        self.assertEqual(get_admin_language(request(accept="pt-PT")), "pt-br")

    def test_then_language_code(self):
        self.assertEqual(get_admin_language(request(accept="ja")), "en")

        with self.settings(LANGUAGE_CODE="nl"):
            self.assertEqual(get_admin_language(request()), "nl")

    def test_a_cookie_for_another_language_is_ignored(self):
        self.assertEqual(get_admin_language(request("ja", "es")), "es")

    @override_settings(LANGUAGES=[("en", "English"), ("nl", "Dutch")])
    def test_only_enabled_languages(self):
        self.assertEqual(get_admin_language(request("de", "fr,nl;q=0.5")), "nl")


class AdminLanguageRequestTests(TestCase):
    def setUp(self):
        user = auth_models.User.objects.create_user(
            username="editor", password="Staff-Secret-42", is_staff=True
        )
        self.client = APIClient()
        self.client.credentials(
            HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}"
        )

    def test_the_page_carries_the_language(self):
        response = self.client.get("/", HTTP_ACCEPT_LANGUAGE="pt-BR")
        html = response.content.decode()

        self.assertIn('<html lang="pt-BR">', html)
        self.assertIn('window.DCS_LANGUAGE = "pt\\u002DBR";', html)
        self.assertEqual(response["Content-Language"], "pt-br")

        languages = json.loads(
            re.search(
                r'<script id="dcs-languages" type="application/json">(.*?)</script>',
                html,
            ).group(1)
        )
        self.assertEqual([language["code"] for language in languages], list(LANGUAGES))
        self.assertIn(
            {"code": "pt-br", "locale": "pt-BR", "name": "Português (Brasil)"},
            languages,
        )

    def test_api_responses_render_in_the_language(self):
        # The error is a lazy string: it renders in German, after the view.
        response = self.client.post(
            "/api/language",
            {"language": "ja"},
            format="json",
            HTTP_ACCEPT_LANGUAGE="de",
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(
            response.json(), {"language": ["Diese Sprache ist nicht verfügbar."]}
        )
        self.assertEqual(response["Content-Language"], "de")

    def test_the_picker_sets_the_cookie(self):
        response = self.client.post("/api/language", {"language": "fr"}, format="json")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json(), {"language": "fr"})
        self.assertEqual(response.cookies["django_language"].value, "fr")

        page = self.client.get("/")
        self.assertIn('<html lang="fr">', page.content.decode())

    def test_the_picker_needs_a_login(self):
        response = APIClient().post("/api/language", {"language": "fr"}, format="json")

        self.assertIn(response.status_code, (401, 403))
        self.assertNotIn("django_language", response.cookies)

    def test_the_language_does_not_leak_out_of_the_request(self):
        from django.utils.translation import get_language

        before = get_language()
        self.client.get("/api/me", HTTP_ACCEPT_LANGUAGE="it")

        self.assertEqual(get_language(), before)


class CatalogTests(SimpleTestCase):
    def test_every_language_has_a_plural_rule_here(self):
        self.assertEqual(set(PLURAL_CATEGORIES), set(LANGUAGES))

    def test_every_language_has_a_frontend_locale(self):
        shipped = {path.name for path in FRONTEND_LOCALES.iterdir()}
        self.assertEqual(shipped, {get_locale(code) for code in LANGUAGES})

    def test_every_language_has_a_django_catalog(self):
        shipped = {path.name for path in DJANGO_LOCALES.iterdir() if path.is_dir()}
        self.assertEqual(
            shipped, {to_locale(code) for code in LANGUAGES if code != "en"}
        )

        for name in shipped:
            for ext in ("po", "mo"):
                self.assertTrue(
                    (DJANGO_LOCALES / name / "LC_MESSAGES" / f"django.{ext}").exists(),
                    f"{name} has no django.{ext}",
                )

    def test_frontend_locales_have_every_string(self):
        english = frontend_strings("en")
        # The strings without their plural forms: "count_one" is "count".
        bases = {PLURAL_SUFFIX.sub("", key) for key in english}
        plurals = {
            PLURAL_SUFFIX.sub("", key) for key in english if PLURAL_SUFFIX.search(key)
        }

        for language, categories in PLURAL_CATEGORIES.items():
            with self.subTest(language=language):
                strings = frontend_strings(language)
                expected = {key for key in bases if key not in plurals} | {
                    f"{key}_{category}" for key in plurals for category in categories
                }

                self.assertEqual(set(strings) - expected, set(), "unknown keys")
                self.assertEqual(expected - set(strings), set(), "missing keys")

                for key, value in strings.items():
                    self.assertTrue(value.strip(), f"{key} is empty")
                    source = (
                        english.get(key) or english[PLURAL_SUFFIX.sub("_other", key)]
                    )
                    self.assertEqual(
                        set(FRONTEND_PLACEHOLDER.findall(value)),
                        set(FRONTEND_PLACEHOLDER.findall(source)),
                        f"{key} has other placeholders than English",
                    )

    def test_django_catalogs_translate_the_same_strings(self):
        catalogs = {}

        for code in LANGUAGES:
            if code == "en":
                continue

            path = DJANGO_LOCALES / to_locale(code) / "LC_MESSAGES" / "django.mo"

            with path.open("rb") as file:
                catalogs[code] = gettext.GNUTranslations(file)._catalog

        msgids = {
            code: {key[0] if isinstance(key, tuple) else key for key in catalog} - {""}
            for code, catalog in catalogs.items()
        }
        reference = msgids["nl"]

        for code, ids in msgids.items():
            with self.subTest(language=code):
                self.assertEqual(ids, reference)

                for key, value in catalogs[code].items():
                    msgid = key[0] if isinstance(key, tuple) else key

                    if not msgid:
                        continue

                    self.assertTrue(value.strip(), f"{msgid!r} is empty")
                    self.assertEqual(
                        set(DJANGO_PLACEHOLDER.findall(value)),
                        set(DJANGO_PLACEHOLDER.findall(msgid)),
                        f"{msgid!r} has other placeholders in {code}",
                    )
