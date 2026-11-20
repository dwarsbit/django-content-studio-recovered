"""
Tests for the public info endpoint.
"""

from django.test import TestCase


class InfoEndpointTests(TestCase):
    def test_info_includes_format_and_widget_names(self):
        """Info serializes every format and widget, including string keys.

        The default mappings carry a string key ("AutoSlugField") next to
        field classes; both must serialize without a 500.
        """
        response = self.client.get("/api/info")

        self.assertEqual(response.status_code, 200)

        data = response.json()
        # Public: nothing that maps the project, like the exact version.
        self.assertNotIn("version", data)
        self.assertIn("CharField", data["formats"])
        self.assertIn("AutoSlugField", data["formats"])
        self.assertIn("AutoSlugField", data["widgets"])

    def test_info_includes_what_the_password_pages_show(self):
        """The password rules and the reset code's lifetime are public."""
        with self.settings(
            AUTH_PASSWORD_VALIDATORS=[
                {
                    "NAME": "django.contrib.auth.password_validation.MinimumLengthValidator",
                    "OPTIONS": {"min_length": 10},
                }
            ],
            CONTENT_STUDIO={"PASSWORD_RESET_EXPIRATION_TIME": 15},
        ):
            data = self.client.get("/api/info").json()

        self.assertEqual(
            data["password_rules"],
            ["Your password must contain at least 10 characters."],
        )
        self.assertEqual(data["password_reset"], {"code_minutes": 15})

    def test_info_has_no_password_reset_without_the_app(self):
        from unittest import mock

        from django.apps import apps

        installed = apps.is_installed

        def without_reset(name):
            return name != "content_studio.contrib.password_reset" and installed(name)

        with mock.patch.object(apps, "is_installed", side_effect=without_reset):
            data = self.client.get("/api/info").json()

        self.assertIsNone(data["password_reset"])
