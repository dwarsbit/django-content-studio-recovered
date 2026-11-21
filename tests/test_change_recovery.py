"""
Keeping unsaved changes in the browser for recovery: the studio's
recover_changes and recover_changes_exclude, the RECOVER_CHANGES and
RECOVERY_MAX_AGE settings, and check W029. The keeping itself happens
in the frontend.
"""

from unittest import mock

from django.contrib.auth import models as auth_models
from django.test import TestCase
from rest_framework.test import APIRequestFactory

from content_studio.admin import AdminSerializer, admin_site
from content_studio.checks import check_content_studio
from tests.testapp.models import Article, Product


def studio(model=Product):
    return admin_site._registry[model]


class RecoverChangesSerializationTests(TestCase):
    def setUp(self):
        self.superuser = auth_models.User.objects.create_superuser(
            username="admin", password="x"
        )

    def serialize(self, model=Product):
        request = APIRequestFactory().get("/")
        request.user = self.superuser
        return AdminSerializer(studio(model)).serialize(request)["edit"]

    def test_on_by_default(self):
        edit = self.serialize()

        self.assertTrue(edit["recover_changes"])
        self.assertEqual(edit["recover_changes_exclude"], [])

    def test_a_studio_opts_out(self):
        with mock.patch.object(studio(), "recover_changes", False):
            self.assertFalse(self.serialize()["recover_changes"])

        self.assertTrue(self.serialize(Article)["recover_changes"])

    def test_the_setting_turns_it_off_everywhere(self):
        with self.settings(CONTENT_STUDIO={"RECOVER_CHANGES": False}):
            self.assertFalse(self.serialize()["recover_changes"])
            self.assertFalse(self.serialize(Article)["recover_changes"])

    def test_excluded_fields_are_serialized(self):
        with mock.patch.object(studio(), "recover_changes_exclude", ["title"]):
            self.assertEqual(self.serialize()["recover_changes_exclude"], ["title"])


class RecoveryMaxAgeTests(TestCase):
    def test_info_has_the_max_age(self):
        data = self.client.get("/api/info").json()
        self.assertEqual(data["settings"]["recovery_max_age"], 7)

        with self.settings(CONTENT_STUDIO={"RECOVERY_MAX_AGE": 2}):
            data = self.client.get("/api/info").json()

        self.assertEqual(data["settings"]["recovery_max_age"], 2)


class RecoverChangesCheckTests(TestCase):
    def messages(self):
        return [m for m in check_content_studio() if m.id == "content_studio.W029"]

    def test_valid_configuration_passes(self):
        with mock.patch.object(studio(), "recover_changes_exclude", ["title"]):
            self.assertEqual(self.messages(), [])

    def test_unknown_field(self):
        with mock.patch.object(
            studio(), "recover_changes_exclude", ["title", "secret_notes"]
        ):
            messages = self.messages()

        self.assertEqual(len(messages), 1)
        self.assertIn("secret_notes", messages[0].msg)
        self.assertIn("is not a field", messages[0].msg)

    def test_not_a_list_of_names(self):
        with mock.patch.object(studio(), "recover_changes_exclude", "title"):
            messages = self.messages()

        self.assertEqual(len(messages), 1)
        self.assertIn("list of field names", messages[0].msg)
