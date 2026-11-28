"""
Tests for branding: the logo, favicon, accent color and login text of the
admin site, the environment badge, their system checks and the
ENVIRONMENT variable of contrib.settings.
"""

from unittest import mock

from django.test import SimpleTestCase, TestCase

from content_studio import branding
from content_studio.admin import ContentStudioSite, admin_site
from content_studio.checks import check_branding


def ids(messages):
    return [message.id for message in messages]


class EnvironmentTests(SimpleTestCase):
    def test_no_environment_shows_no_badge(self):
        self.assertIsNone(branding.resolve_environment(None))
        self.assertIsNone(branding.resolve_environment(""))
        self.assertIsNone(branding.resolve_environment("  "))

    def test_known_names_have_a_label_and_a_tone(self):
        self.assertEqual(
            branding.resolve_environment("staging"),
            {"label": "Staging", "color": "yellow"},
        )
        self.assertEqual(
            branding.resolve_environment("Development"),
            {"label": "Development", "color": "blue"},
        )
        self.assertEqual(
            branding.resolve_environment("dev"),
            {"label": "Development", "color": "blue"},
        )
        self.assertEqual(
            branding.resolve_environment("test"),
            {"label": "Test", "color": "yellow"},
        )

    def test_production_shows_no_badge(self):
        for name in ("production", "Production", "prod", "live"):
            with self.subTest(name=name):
                self.assertIsNone(branding.resolve_environment(name))

    def test_an_unknown_name_is_a_gray_badge(self):
        self.assertEqual(
            branding.resolve_environment("demo"),
            {"label": "Demo", "color": "gray"},
        )

    def test_a_dict_sets_label_and_color(self):
        self.assertEqual(
            branding.resolve_environment({"label": "Production", "color": "red"}),
            {"label": "Production", "color": "red"},
        )
        self.assertEqual(
            branding.resolve_environment({"label": "Preview"}),
            {"label": "Preview", "color": "gray"},
        )

    def test_invalid_values_show_no_badge_and_are_errors(self):
        for value in (
            42,
            {"color": "red"},
            {"label": "Staging", "color": "orange"},
            {"label": "Staging", "colour": "red"},
        ):
            with self.subTest(value=value):
                self.assertIsNone(branding.resolve_environment(value))
                self.assertTrue(branding.environment_errors(value))

    def test_the_site_can_pick_the_environment_per_request(self):
        class Site(ContentStudioSite):
            def get_environment(self, request):
                return "staging" if request.get_host() == "staging.test" else None

        site = Site()
        request = mock.Mock(get_host=lambda: "staging.test")

        self.assertEqual(branding.get_environment(site, request)["label"], "Staging")
        request.get_host = lambda: "example.com"
        self.assertIsNone(branding.get_environment(site, request))


class AccentTests(SimpleTestCase):
    def site(self, **attrs):
        return type("Site", (ContentStudioSite,), attrs)()

    def test_no_accent_without_a_color(self):
        site = self.site()

        self.assertIsNone(branding.get_accent(site))
        self.assertEqual(branding.accent_css(site), "")

    def test_one_color_serves_both_themes_with_a_readable_foreground(self):
        accent = branding.get_accent(self.site(accent_color="#4F46E5"))

        self.assertEqual(
            accent,
            {
                "light": {"color": "#4f46e5", "foreground": "#ffffff"},
                "dark": {"color": "#4f46e5", "foreground": "#ffffff"},
            },
        )

    def test_the_dark_color_replaces_it_in_the_dark_theme(self):
        accent = branding.get_accent(
            self.site(accent_color="rgb(79, 70, 229)", accent_color_dark="#818cf8")
        )

        self.assertEqual(accent["light"]["color"], "#4f46e5")
        self.assertEqual(accent["dark"], {"color": "#818cf8", "foreground": "#000000"})

    def test_css_sets_the_primary_variables_per_theme(self):
        css = branding.accent_css(
            self.site(accent_color="#4f46e5", accent_color_dark="#818cf8")
        )

        self.assertIn(":root{--primary:#4f46e5;--primary-foreground:#ffffff;", css)
        self.assertIn(":root.dark{--primary:#818cf8;--primary-foreground:#000000;", css)
        self.assertIn("--ring:#4f46e5;", css)

    def test_a_color_that_does_not_parse_is_left_out(self):
        site = self.site(accent_color="red;}body{display:none")

        self.assertIsNone(branding.get_accent(site))
        self.assertEqual(branding.accent_css(site), "")
        self.assertEqual(
            branding.accent_errors(site), [("accent_color", "red;}body{display:none")]
        )

    def test_low_contrast_is_reported_per_theme(self):
        # Pale yellow on white; dark navy on the dark background.
        self.assertEqual(
            [
                (attr, theme)
                for attr, theme, _ in branding.accent_warnings(
                    self.site(accent_color="#fde68a")
                )
            ],
            [("accent_color", "light")],
        )
        self.assertEqual(
            [
                (attr, theme)
                for attr, theme, _ in branding.accent_warnings(
                    self.site(accent_color="#1e1b4b")
                )
            ],
            [("accent_color", "dark")],
        )
        self.assertEqual(
            branding.accent_warnings(
                self.site(accent_color="#1e1b4b", accent_color_dark="#818cf8")
            ),
            [],
        )

    def test_contrast(self):
        self.assertAlmostEqual(branding.contrast("#000000", "#ffffff"), 21)
        self.assertAlmostEqual(branding.contrast("#777777", "#777777"), 1)


class AssetTests(SimpleTestCase):
    def test_urls_are_kept_and_static_paths_resolved(self):
        self.assertEqual(
            branding.asset_url("https://cdn.example.com/logo.svg"),
            "https://cdn.example.com/logo.svg",
        )
        self.assertEqual(branding.asset_url("/media/logo.svg"), "/media/logo.svg")
        self.assertEqual(
            branding.asset_url("content_studio/img/icon.svg"),
            "/static/content_studio/img/icon.svg",
        )
        self.assertIsNone(branding.asset_url(None))
        self.assertIsNone(branding.asset_url(""))

    def test_missing_static_files(self):
        site = type(
            "Site",
            (ContentStudioSite,),
            {
                "site_logo": "northbound/logo.svg",
                "site_logo_dark": "northbound/missing.svg",
                "site_favicon": "https://example.com/favicon.png",
            },
        )()

        with mock.patch.object(
            branding.finders, "find", lambda path: path == "northbound/logo.svg"
        ):
            self.assertEqual(
                branding.missing_static_files(site),
                [("site_logo_dark", "northbound/missing.svg")],
            )


class BrandingChecksTests(SimpleTestCase):
    def test_defaults_pass(self):
        self.assertEqual(check_branding(), [])

    def test_errors_and_warnings(self):
        with (
            mock.patch.object(admin_site, "accent_color", "not a color"),
            mock.patch.object(admin_site, "site_logo", "northbound/missing.svg"),
            self.settings(CONTENT_STUDIO={"ENVIRONMENT": {"label": "Staging"}}),
        ):
            self.assertEqual(
                ids(check_branding()), ["content_studio.E068", "content_studio.W044"]
            )

        with self.settings(CONTENT_STUDIO={"ENVIRONMENT": {"color": "orange"}}):
            self.assertEqual(
                ids(check_branding()), ["content_studio.E068", "content_studio.E068"]
            )

        with mock.patch.object(admin_site, "accent_color", "#fde68a"):
            self.assertEqual(ids(check_branding()), ["content_studio.W045"])


class BrandingEndpointTests(TestCase):
    def test_info_sends_the_branding(self):
        with (
            mock.patch.object(admin_site, "site_logo", "content_studio/img/icon.svg"),
            mock.patch.object(admin_site, "login_text", "Use your Northbound account."),
            self.settings(CONTENT_STUDIO={"ENVIRONMENT": "staging"}),
        ):
            data = self.client.get("/api/info").json()

        self.assertEqual(
            data["branding"],
            {
                "logo": "/static/content_studio/img/icon.svg",
                "logo_dark": None,
                "login_text": "Use your Northbound account.",
                "environment": {"label": "Staging", "color": "yellow"},
            },
        )

    def test_info_defaults(self):
        data = self.client.get("/api/info").json()

        self.assertEqual(
            data["branding"],
            {"logo": None, "logo_dark": None, "login_text": None, "environment": None},
        )

    def test_page_renders_title_favicon_and_accent(self):
        with (
            mock.patch.object(admin_site, "site_title", "Northbound CMS"),
            mock.patch.object(admin_site, "site_favicon", "northbound/favicon.png"),
            mock.patch.object(admin_site, "accent_color", "#4f46e5"),
            self.settings(CONTENT_STUDIO={"ENVIRONMENT": "staging"}),
        ):
            page = self.client.get("/").content.decode()

        self.assertIn("<title>[Staging] Northbound CMS</title>", page)
        self.assertIn('<link rel="icon" href="/static/northbound/favicon.png">', page)
        self.assertIn('<style id="dcs-accent">:root{--primary:#4f46e5;', page)

    def test_page_defaults(self):
        page = self.client.get("/").content.decode()

        self.assertIn("<title>Content Studio</title>", page)
        self.assertIn("content_studio/img/favicon.png", page)
        self.assertNotIn("dcs-accent", page)

    def test_production_has_no_prefix(self):
        with self.settings(CONTENT_STUDIO={"ENVIRONMENT": "production"}):
            page = self.client.get("/").content.decode()

        self.assertIn("<title>Content Studio</title>", page)


class EnvironmentVariableTests(SimpleTestCase):
    def configure(self, environ):
        from pathlib import Path

        from content_studio.contrib.settings import configure

        return configure(
            {},
            base_dir=Path("/srv"),
            env={
                "DJANGO_SECRET_KEY": "k3Y-9vQ!r2#Lm7@pX4$wZ8^tN1&bH6*sD0(fJ5)gU"
                + "a" * 10,
                **environ,
            },
        )["CONTENT_STUDIO"]

    def test_environment_sets_the_badge_and_sentry(self):
        settings = self.configure({"ENVIRONMENT": "staging"})

        self.assertEqual(settings["ENVIRONMENT"], "staging")
        self.assertEqual(settings["SENTRY_ENVIRONMENT"], "staging")

    def test_no_environment_sets_neither(self):
        settings = self.configure({})

        self.assertNotIn("ENVIRONMENT", settings)
        self.assertNotIn("SENTRY_ENVIRONMENT", settings)
