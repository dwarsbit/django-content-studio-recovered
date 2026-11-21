"""
Tests for unpublished changes (content_studio.pending): edits to
published objects of a studio with Publishing(pending_changes=True)
stay out of sight until Publish changes.

FeatureAdmin uses them; StoryAdmin (test_publishing) does not.
"""

import datetime
from unittest import mock

from django.apps import apps
from django.contrib.admin.models import LogEntry
from django.contrib.auth import models as auth_models
from django.core.files.base import ContentFile
from django.core.files.storage import default_storage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import admin_site
from content_studio.checks import publishing_errors
from content_studio.history.models import PendingChanges, Version
from content_studio.publishing import Publishing
from content_studio.signals import content_changed
from content_studio.token_backends.jwt import create_access_token
from content_studio.uploads import clear_expired_uploads
from tests.testapp.models import Category, Feature, Story

NOW = timezone.now()
HOUR = datetime.timedelta(hours=1)
URL = "/api/content/testapp.feature"


class PendingTestCase(TestCase):
    def setUp(self):
        self.superuser = auth_models.User.objects.create_superuser(
            username="admin", password="x", first_name="Ada", last_name="Admin"
        )
        self.client = self.client_for(self.superuser)
        type(admin_site._registry[Feature]).saves = []
        self.travel = Category.objects.create(name="Travel")
        self.design = Category.objects.create(name="Design")
        self.feature = Feature.objects.create(
            title="Slow trains",
            summary="Fast trains get you there.",
            section=self.travel,
            published_at=NOW - HOUR,
        )
        self.feature.categories.set([self.travel])

    def tearDown(self):
        clear_expired_uploads(max_age=datetime.timedelta(minutes=-1))

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def staff(self, *codenames, username="editor"):
        user = auth_models.User.objects.create_user(
            username=username, password="x", is_staff=True
        )
        user.user_permissions.set(
            auth_models.Permission.objects.filter(codename__in=codenames)
        )
        return user

    def detail(self, client=None, feature=None):
        response = (client or self.client).get(f"{URL}/{(feature or self.feature).pk}")
        assert response.status_code == 200, response.content
        return response.json()

    def save(self, client=None, feature=None, **changes):
        feature = feature or self.feature
        data = {
            key: value
            for key, value in self.detail(client, feature).items()
            if not key.startswith("__")
        }
        data.update(changes)
        return (client or self.client).put(f"{URL}/{feature.pk}", data, format="json")

    def publishing(self, action, client=None, **data):
        return (client or self.client).post(
            f"{URL}/{self.feature.pk}/publishing",
            {"action": action, **data},
            format="json",
        )


class SaveTests(PendingTestCase):
    def test_saving_a_live_object_keeps_the_changes_unpublished(self):
        response = self.save(title="Slow journeys", summary="Slow trains too.")

        assert response.status_code == 200, response.content
        data = response.json()
        # The edit page shows the changes...
        assert data["title"] == "Slow journeys"
        assert data["summary"] == "Slow trains too."
        pending = data["__publishing__"]["pending"]
        assert data["__publishing__"]["has_pending"] is True
        assert pending["fields"] == ["title", "summary"]
        assert pending["edited_by"] == "Ada Admin"
        assert pending["live"] == {
            "title": "Slow trains",
            "summary": "Fast trains get you there.",
        }
        # ...the object keeps its published values.
        self.feature.refresh_from_db()
        assert self.feature.title == "Slow trains"
        assert self.feature.summary == "Fast trains get you there."
        # The studio's save hooks wait for the publish.
        assert admin_site._registry[Feature].saves == []

    def test_reloading_shows_the_changes(self):
        self.save(title="Slow journeys")

        data = self.detail()
        assert data["title"] == "Slow journeys"
        assert data["__publishing__"]["pending"]["fields"] == ["title"]

    def test_detail_without_changes(self):
        data = self.detail()

        assert data["__publishing__"]["has_pending"] is False
        assert data["__publishing__"]["pending"] is None

    def test_relations_are_held_too(self):
        response = self.save(
            section={"id": self.design.pk},
            categories=[{"id": self.travel.pk}, {"id": self.design.pk}],
        )

        assert response.status_code == 200, response.content
        data = response.json()
        assert data["__publishing__"]["pending"]["fields"] == [
            "section",
            "categories",
        ]
        assert data["section"]["id"] == self.design.pk
        assert {row["id"] for row in data["categories"]} == {
            self.travel.pk,
            self.design.pk,
        }
        self.feature.refresh_from_db()
        assert self.feature.section == self.travel
        assert list(self.feature.categories.all()) == [self.travel]

    def test_changing_a_field_back_drops_it(self):
        self.save(title="Slow journeys", summary="Slow trains too.")
        response = self.save(title="Slow trains")

        assert response.json()["__publishing__"]["pending"]["fields"] == ["summary"]

        response = self.save(summary="Fast trains get you there.")

        assert response.json()["__publishing__"]["has_pending"] is False
        assert not PendingChanges.objects.exists()

    def test_the_models_validation_runs_on_save(self):
        Feature.objects.create(title="Taken")

        response = self.save(title="Taken")

        assert response.status_code == 400
        assert "title" in response.json()
        assert not PendingChanges.objects.exists()

    def test_saving_is_logged_without_a_content_change(self):
        received = []

        def receiver(sender, changes, **kwargs):
            received.extend(changes)

        content_changed.connect(receiver)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                self.save(title="Slow journeys")
        finally:
            content_changed.disconnect(receiver)

        assert received == []
        entry = LogEntry.objects.latest("pk")
        assert entry.change_message == "Saved unpublished changes."
        # Not a version: the published object did not change.
        assert not Version.objects.exists()

    def test_drafts_and_scheduled_objects_save_as_before(self):
        draft = Feature.objects.create(title="Draft")
        scheduled = Feature.objects.create(title="Later", published_at=NOW + HOUR)

        for feature in (draft, scheduled):
            response = self.save(feature=feature, summary="Saved.")

            assert response.status_code == 200, response.content
            feature.refresh_from_db()
            assert feature.summary == "Saved."

        assert not PendingChanges.objects.exists()

    def test_other_studios_save_live_objects_as_before(self):
        story = Story.objects.create(title="Live", published_at=NOW - HOUR)

        response = self.client.patch(
            f"/api/content/testapp.story/{story.pk}",
            {"title": "Changed"},
            format="json",
        )

        assert response.status_code == 200, response.content
        story.refresh_from_db()
        assert story.title == "Changed"

    def test_a_new_file_is_kept_until_published(self):
        token = self.client.post(
            f"{URL}/uploads/attachment",
            {"file": SimpleUploadedFile("guide.pdf", b"%PDF guide")},
            format="multipart",
        ).json()["upload"]

        response = self.save(attachment={"upload": token})

        assert response.status_code == 200, response.content
        assert response.json()["attachment"]["name"].startswith("guide")
        self.feature.refresh_from_db()
        assert not self.feature.attachment
        pending = PendingChanges.objects.get()
        stored = pending.data["attachment"]["stored"]
        assert default_storage.exists(stored)

        # Saving again sends the file back as shown: it stays.
        self.save(summary="With a guide.")
        assert PendingChanges.objects.get().data["attachment"] == {"stored": stored}

        assert self.publishing("publish_changes").status_code == 200
        self.feature.refresh_from_db()
        assert self.feature.attachment.name == stored
        assert self.feature.attachment.read() == b"%PDF guide"

    def test_discarding_removes_a_kept_file(self):
        token = self.client.post(
            f"{URL}/uploads/attachment",
            {"file": SimpleUploadedFile("draft.pdf", b"%PDF draft")},
            format="multipart",
        ).json()["upload"]
        self.save(attachment={"upload": token})
        stored = PendingChanges.objects.get().data["attachment"]["stored"]

        assert self.publishing("discard_changes").status_code == 200
        assert not default_storage.exists(stored)


class PublishTests(PendingTestCase):
    def test_publish_changes_saves_them_the_regular_way(self):
        response = self.save(title="Slow journeys", categories=[{"id": self.design.pk}])
        assert response.status_code == 200, response.content

        received = []

        def receiver(sender, changes, **kwargs):
            received.extend(change.action for change in changes)

        content_changed.connect(receiver)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                response = self.publishing("publish_changes")
        finally:
            content_changed.disconnect(receiver)

        assert response.status_code == 200, response.content
        assert response.json()["has_pending"] is False
        self.feature.refresh_from_db()
        assert self.feature.title == "Slow journeys"
        assert list(self.feature.categories.all()) == [self.design]
        assert admin_site._registry[Feature].saves == ["Slow journeys"]
        assert received == ["updated"]
        assert not PendingChanges.objects.exists()
        # The history keeps the published change as a version.
        version = Version.objects.get()
        assert "title" in version.fields

    def test_publish_changes_needs_the_publish_permission(self):
        editor = self.staff("view_feature", "change_feature")
        client = self.client_for(editor)
        self.save(client=client, title="Slow journeys")

        response = self.publishing("publish_changes", client=client)

        assert response.status_code == 403
        assert PendingChanges.objects.exists()

    def test_editors_without_publish_permission_save_changes(self):
        editor = self.staff("view_feature", "change_feature")

        response = self.save(client=self.client_for(editor), title="By an editor")

        assert response.status_code == 200, response.content
        assert response.json()["__publishing__"]["pending"]["edited_by"] == "editor"
        self.feature.refresh_from_db()
        assert self.feature.title == "Slow trains"

    def test_publish_changes_without_changes(self):
        response = self.publishing("publish_changes")

        assert response.status_code == 400

    def test_changes_that_no_longer_validate_are_refused(self):
        self.save(title="Slow journeys")
        Feature.objects.create(title="Slow journeys 2")
        PendingChanges.objects.update(
            data={"title": "Slow journeys 2"}, values={"title": "Slow journeys 2"}
        )

        response = self.publishing("publish_changes")

        assert response.status_code == 400
        assert PendingChanges.objects.exists()

    def test_discard_changes(self):
        self.save(title="Slow journeys")

        response = self.publishing("discard_changes")

        assert response.status_code == 200, response.content
        assert not PendingChanges.objects.exists()
        assert self.detail()["title"] == "Slow trains"
        assert (
            LogEntry.objects.latest("pk").change_message
            == "Discarded the unpublished changes."
        )

    def test_discard_needs_change_permission(self):
        self.save(title="Slow journeys")
        viewer = self.staff("view_feature", username="viewer")

        response = self.publishing("discard_changes", client=self.client_for(viewer))

        assert response.status_code == 403
        assert PendingChanges.objects.exists()

    def test_unpublishing_keeps_the_changes_in_the_draft(self):
        self.save(title="Slow journeys")

        response = self.publishing("unpublish")

        assert response.status_code == 200, response.content
        self.feature.refresh_from_db()
        assert self.feature.published_at is None
        assert self.feature.title == "Slow journeys"
        assert not PendingChanges.objects.exists()

    def test_scheduling_again_keeps_the_changes(self):
        self.save(summary="Later.")

        response = self.publishing("schedule", at=(NOW + 2 * HOUR).isoformat())

        assert response.status_code == 200, response.content
        self.feature.refresh_from_db()
        assert self.feature.summary == "Later."
        assert not PendingChanges.objects.exists()

    def test_publishing_again_takes_the_changes(self):
        self.save(title="Slow journeys")
        # It expired with the changes; publishing it again takes them.
        Feature.objects.filter(pk=self.feature.pk).update(published_at=None)

        response = self.publishing("publish")

        assert response.status_code == 200, response.content
        assert response.json()["has_pending"] is False
        self.feature.refresh_from_db()
        assert self.feature.published_at is not None
        assert self.feature.title == "Slow journeys"

    def test_saving_an_object_that_is_not_live_takes_its_changes(self):
        self.save(title="Slow journeys")
        # It expired, say: no longer live, its edit page shows the changes.
        Feature.objects.filter(pk=self.feature.pk).update(published_at=None)

        response = self.save(summary="Saved as a draft.")

        assert response.status_code == 200, response.content
        self.feature.refresh_from_db()
        assert self.feature.title == "Slow journeys"
        assert self.feature.summary == "Saved as a draft."
        assert not PendingChanges.objects.exists()


class ListTests(PendingTestCase):
    def test_rows_say_which_have_changes(self):
        other = Feature.objects.create(title="Other", published_at=NOW - HOUR)
        self.save(title="Slow journeys")

        rows = {
            row["id"]: row["__publishing__"]
            for row in self.client.get(URL).json()["results"]
        }

        assert rows[self.feature.pk]["has_pending"] is True
        assert rows[other.pk]["has_pending"] is False
        # The list shows the published title.
        titles = [row["title"] for row in self.client.get(URL).json()["results"]]
        assert "Slow trains" in titles

    def test_status_filter_finds_objects_with_changes(self):
        Feature.objects.create(title="Other", published_at=NOW - HOUR)
        self.save(title="Slow journeys")

        response = self.client.get(f"{URL}?publishing_status=pending")

        assert response.status_code == 200, response.content
        assert [row["id"] for row in response.json()["results"]] == [self.feature.pk]


class CheckTests(TestCase):
    def test_pending_changes_need_the_history_app(self):
        class FeatureStudio:
            model = Feature
            publishing = Publishing("published_at", pending_changes=True)

        original = apps.is_installed

        def is_installed(name):
            return False if name == "content_studio.history" else original(name)

        with mock.patch.object(apps, "is_installed", is_installed):
            errors = publishing_errors(FeatureStudio())

        assert any("pending_changes" in message for _id, message in errors)
