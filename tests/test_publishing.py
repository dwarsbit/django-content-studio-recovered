"""
Tests for draft, publish and scheduling (content_studio.publishing).

StoryAdmin configures publishing on a plain model with an unpublish date
and a status field kept in step; BulletinAdmin uses the PublishableModel
base model with only a publish date.
"""

import datetime
from types import SimpleNamespace
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import models as auth_models
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, ModelStudio, admin_site
from content_studio.checks import publishing_errors
from content_studio.publishing import (
    DRAFT,
    EXPIRED,
    PUBLISHED,
    SCHEDULED,
    Publishing,
    get_state,
    live,
    run_scheduled,
)
from content_studio.signals import content_changed
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Bulletin, Note, Story

NOW = timezone.now()
HOUR = datetime.timedelta(hours=1)


def story_config():
    return admin_site._registry[Story].publishing


class PublishingTestCase(TestCase):
    def setUp(self):
        self.superuser = auth_models.User.objects.create_superuser(
            username="admin", password="x"
        )
        self.client = self.client_for(self.superuser)
        type(admin_site._registry[Story]).published = []
        type(admin_site._registry[Story]).unpublished = []

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def staff(self, *codenames, username="staff"):
        user = auth_models.User.objects.create_user(
            username=username, password="x", is_staff=True
        )
        user.user_permissions.set(
            auth_models.Permission.objects.filter(codename__in=codenames)
        )
        return user

    def publish(self, story, action, client=None, **data):
        return (client or self.client).post(
            f"/api/content/testapp.story/{story.pk}/publishing",
            {"action": action, **data},
            format="json",
        )


class StateTests(PublishingTestCase):
    def test_states_follow_the_dates(self):
        config = story_config()
        cases = [
            (Story(published_at=None), DRAFT),
            (Story(published_at=NOW + HOUR), SCHEDULED),
            (Story(published_at=NOW - HOUR), PUBLISHED),
            (Story(published_at=NOW - HOUR, unpublish_at=NOW + HOUR), PUBLISHED),
            (Story(published_at=NOW - 2 * HOUR, unpublish_at=NOW - HOUR), EXPIRED),
        ]

        for story, state in cases:
            self.assertEqual(get_state(config, story, NOW), state)

    def test_live_filters_published_objects(self):
        Story.objects.create(title="draft")
        Story.objects.create(title="soon", published_at=NOW + HOUR)
        Story.objects.create(title="live", published_at=NOW - HOUR)
        Story.objects.create(
            title="gone", published_at=NOW - 2 * HOUR, unpublish_at=NOW - HOUR
        )

        titles = set(
            live(Story.objects.all(), admin_site._registry[Story]).values_list(
                "title", flat=True
            )
        )

        self.assertEqual(titles, {"live"})

    def test_publishable_model_queryset(self):
        Bulletin.objects.create(title="draft")
        Bulletin.objects.create(title="soon", published_at=NOW + HOUR)
        live_one = Bulletin.objects.create(title="live", published_at=NOW - HOUR)
        Bulletin.objects.create(
            title="gone", published_at=NOW - 2 * HOUR, unpublish_at=NOW - HOUR
        )

        self.assertEqual(list(Bulletin.objects.live()), [live_one])
        self.assertEqual(Bulletin.objects.drafts().get().title, "draft")
        self.assertEqual(Bulletin.objects.scheduled().get().title, "soon")
        self.assertEqual(Bulletin.objects.expired().get().title, "gone")
        self.assertTrue(live_one.is_live)
        self.assertEqual(live_one.publishing_status, PUBLISHED)

    def test_publish_permission_is_created(self):
        self.assertTrue(
            auth_models.Permission.objects.filter(
                codename="publish_story",
                content_type=ContentType.objects.get_for_model(Story),
            ).exists()
        )
        self.assertTrue(
            auth_models.Permission.objects.filter(codename="publish_bulletin").exists()
        )


class AdminPayloadTests(PublishingTestCase):
    def test_list_has_status_column_filter_and_actions(self):
        request = SimpleNamespace(user=self.superuser)
        data = AdminSerializer(admin_site._registry[Story]).serialize(request)

        names = [column["name"] for column in data["list"]["display"]]
        # The status field's column becomes the Status column.
        self.assertEqual(names, ["title", "__publishing__"])
        self.assertEqual(data["list"]["filter"][0]["name"], "publishing_status")
        self.assertEqual(
            data["list"]["publishing"], {"unpublish": True, "can_publish": True}
        )
        action_ids = [action["id"] for action in data["list"]["actions"]]
        self.assertIn("publishing:publish", action_ids)
        self.assertIn("publishing:schedule", action_ids)
        self.assertIn("publishing:unpublish", action_ids)

    def test_bulletin_column_follows_first_column(self):
        request = SimpleNamespace(user=self.superuser)
        data = AdminSerializer(admin_site._registry[Bulletin]).serialize(request)

        names = [column["name"] for column in data["list"]["display"]]
        self.assertEqual(names, ["title", "__publishing__"])
        self.assertFalse(data["list"]["publishing"]["unpublish"])

    def test_studios_without_publishing_are_unchanged(self):
        request = SimpleNamespace(user=self.superuser)
        data = AdminSerializer(admin_site._registry[Note]).serialize(request)

        self.assertIsNone(data["list"]["publishing"])
        self.assertNotIn(
            "publishing:publish", [a["id"] for a in data["list"]["actions"]]
        )

    def test_list_rows_carry_their_state(self):
        Story.objects.create(title="soon", published_at=NOW + HOUR)

        response = self.client.get("/api/content/testapp.story")

        row = response.json()["results"][0]
        self.assertEqual(row["__publishing__"]["state"], SCHEDULED)

    def test_list_filters_on_state(self):
        Story.objects.create(title="draft")
        Story.objects.create(title="soon", published_at=NOW + HOUR)
        Story.objects.create(title="live", published_at=NOW - HOUR)

        response = self.client.get(
            "/api/content/testapp.story?publishing_status=draft"
            "&publishing_status=scheduled"
        )

        titles = {row["title"] for row in response.json()["results"]}
        self.assertEqual(titles, {"draft", "soon"})

    def test_detail_carries_state_and_permission(self):
        story = Story.objects.create(title="soon", published_at=NOW + HOUR)

        response = self.client.get(f"/api/content/testapp.story/{story.pk}")

        data = response.json()["__publishing__"]
        self.assertEqual(data["state"], SCHEDULED)
        self.assertTrue(data["can_publish"])

    def test_form_never_writes_publishing_fields(self):
        story = Story.objects.create(title="draft")

        response = self.client.patch(
            f"/api/content/testapp.story/{story.pk}",
            {
                "title": "renamed",
                "published_at": (NOW - HOUR).isoformat(),
                "status": "live",
            },
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        story.refresh_from_db()
        self.assertEqual(story.title, "renamed")
        self.assertIsNone(story.published_at)
        self.assertEqual(story.status, "draft")
        self.assertIn("published_at", response.json()["__readonly_fields__"])

    def test_view_on_site_is_hidden_until_live(self):
        story = Story.objects.create(title="draft")

        with mock.patch.object(
            admin_site._registry[Story], "get_link_url", return_value="/s/1/"
        ):
            draft = self.client.get(f"/api/content/testapp.story/{story.pk}").json()
            Story.objects.filter(pk=story.pk).update(published_at=NOW - HOUR)
            published = self.client.get(f"/api/content/testapp.story/{story.pk}").json()

        self.assertIsNone(draft["__view_on_site__"])
        self.assertEqual(published["__view_on_site__"], "/s/1/")


class EndpointTests(PublishingTestCase):
    def test_publish_now(self):
        story = Story.objects.create(title="draft")

        response = self.publish(story, "publish")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state"], PUBLISHED)
        story.refresh_from_db()
        self.assertIsNotNone(story.published_at)
        self.assertEqual(story.status, "live")
        entry = LogEntry.objects.get(object_id=str(story.pk))
        self.assertEqual(entry.change_message, "Published.")
        self.assertEqual(
            type(admin_site._registry[Story]).published, [(True, story.pk)]
        )

    def test_publish_sends_published_change(self):
        story = Story.objects.create(title="draft")
        received = []

        def receiver(sender, changes, **kwargs):
            received.extend(change.action for change in changes)

        content_changed.connect(receiver)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                self.publish(story, "publish")
        finally:
            content_changed.disconnect(receiver)

        self.assertEqual(received, ["published"])

    def test_schedule_with_unpublish_date(self):
        story = Story.objects.create(title="draft")
        at = NOW + datetime.timedelta(days=2)
        until = at + datetime.timedelta(days=7)

        response = self.publish(
            story, "schedule", at=at.isoformat(), unpublish_at=until.isoformat()
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["state"], SCHEDULED)
        story.refresh_from_db()
        self.assertEqual(story.published_at, at)
        self.assertEqual(story.unpublish_at, until)
        self.assertEqual(story.status, "draft")
        self.assertTrue(
            LogEntry.objects.get(object_id=str(story.pk)).change_message.startswith(
                "Scheduled to publish on "
            )
        )

    def test_schedule_refuses_the_past_and_a_late_publish_date(self):
        story = Story.objects.create(title="draft")

        past = self.publish(story, "schedule", at=(NOW - HOUR).isoformat())
        late = self.publish(
            story,
            "schedule",
            at=(NOW + 2 * HOUR).isoformat(),
            unpublish_at=(NOW + HOUR).isoformat(),
        )

        self.assertEqual(past.status_code, 400)
        self.assertIn("at", past.json())
        self.assertEqual(late.status_code, 400)
        self.assertIn("unpublish_at", late.json())
        story.refresh_from_db()
        self.assertIsNone(story.published_at)

    def test_unpublish_and_cancel_schedule(self):
        live_story = Story.objects.create(
            title="live", published_at=NOW - HOUR, status="live"
        )
        soon = Story.objects.create(title="soon", published_at=NOW + HOUR)

        self.publish(live_story, "unpublish")
        self.publish(soon, "unpublish")

        live_story.refresh_from_db()
        soon.refresh_from_db()
        self.assertIsNone(live_story.published_at)
        self.assertEqual(live_story.status, "draft")
        self.assertIsNone(soon.published_at)
        messages = dict(LogEntry.objects.values_list("object_id", "change_message"))
        self.assertEqual(messages[str(live_story.pk)], "Unpublished.")
        self.assertEqual(messages[str(soon.pk)], "Unscheduled.")
        self.assertEqual(
            type(admin_site._registry[Story]).unpublished, [(True, live_story.pk)]
        )

    def test_set_unpublish_date(self):
        story = Story.objects.create(title="live", published_at=NOW - HOUR)
        until = NOW + datetime.timedelta(days=1)

        response = self.publish(
            story, "set_unpublish_at", unpublish_at=until.isoformat()
        )
        cleared = self.publish(story, "set_unpublish_at", unpublish_at=None)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["unpublish_at"], until.isoformat())
        self.assertIsNone(cleared.json()["unpublish_at"])

    def test_publishing_an_expired_story_clears_its_unpublish_date(self):
        story = Story.objects.create(
            title="gone", published_at=NOW - 2 * HOUR, unpublish_at=NOW - HOUR
        )

        self.publish(story, "publish")

        story.refresh_from_db()
        self.assertIsNone(story.unpublish_at)
        self.assertEqual(get_state(story_config(), story), PUBLISHED)

    def test_needs_the_publish_permission(self):
        story = Story.objects.create(title="draft")
        editor = self.staff("view_story", "change_story", username="editor")
        publisher = self.staff(
            "view_story", "change_story", "publish_story", username="publisher"
        )

        refused = self.publish(story, "publish", client=self.client_for(editor))
        detail = self.client_for(editor).get(f"/api/content/testapp.story/{story.pk}")
        allowed = self.publish(story, "publish", client=self.client_for(publisher))

        self.assertEqual(refused.status_code, 403)
        self.assertFalse(detail.json()["__publishing__"]["can_publish"])
        self.assertEqual(allowed.status_code, 200)

    def test_unknown_action(self):
        story = Story.objects.create(title="draft")

        self.assertEqual(self.publish(story, "launch").status_code, 400)

    def test_model_without_publishing_has_no_endpoint(self):
        note = Note.objects.create(title="note")

        response = self.client.post(
            f"/api/content/testapp.note/{note.pk}/publishing",
            {"action": "publish"},
            format="json",
        )

        self.assertEqual(response.status_code, 404)


class BulkActionTests(PublishingTestCase):
    def bulk(self, action, ids, client=None, data=None):
        return (client or self.client).post(
            "/api/content/testapp.story/bulk",
            {"action": action, "ids": ids, **({"data": data} if data else {})},
            format="json",
        )

    def test_publish_now_skips_published(self):
        draft = Story.objects.create(title="draft")
        live_story = Story.objects.create(title="live", published_at=NOW - HOUR)

        response = self.bulk("publishing:publish", [draft.pk, live_story.pk])

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["message"], "Published 1 items.")
        draft.refresh_from_db()
        self.assertEqual(get_state(story_config(), draft), PUBLISHED)

    def test_schedule_and_unpublish(self):
        one = Story.objects.create(title="one")
        two = Story.objects.create(title="two", published_at=NOW - HOUR)
        at = NOW + datetime.timedelta(days=1)

        scheduled = self.bulk(
            "publishing:schedule", [one.pk, two.pk], data={"at": at.isoformat()}
        )
        unpublished = self.bulk("publishing:unpublish", [one.pk, two.pk])

        self.assertEqual(scheduled.status_code, 200, scheduled.content)
        self.assertEqual(unpublished.json()["message"], "Unpublished 2 items.")
        self.assertFalse(Story.objects.exclude(published_at=None).exists())

    def test_bulk_publishing_needs_the_permission(self):
        story = Story.objects.create(title="draft")
        editor = self.staff("view_story", "change_story", username="editor")

        response = self.bulk(
            "publishing:publish", [story.pk], client=self.client_for(editor)
        )

        self.assertEqual(response.status_code, 404)


class ScheduledRunTests(PublishingTestCase):
    def schedule(self, story, at):
        """Schedule through the endpoint, then move the dates as if time
        passed."""
        self.publish(story, "schedule", at=(NOW + HOUR).isoformat())
        Story.objects.filter(pk=story.pk).update(published_at=at)
        story.refresh_from_db()

    def test_records_content_that_went_live(self):
        story = Story.objects.create(title="soon")
        self.schedule(story, timezone.now() - datetime.timedelta(minutes=1))
        received = []

        def receiver(sender, changes, **kwargs):
            received.extend((change.action, change.user) for change in changes)

        content_changed.connect(receiver)
        try:
            with self.captureOnCommitCallbacks(execute=True):
                result = run_scheduled()
        finally:
            content_changed.disconnect(receiver)

        self.assertEqual(result, {"published": 1, "unpublished": 0})
        story.refresh_from_db()
        self.assertEqual(story.status, "live")
        entry = LogEntry.objects.filter(object_id=str(story.pk)).latest("action_time")
        self.assertEqual(entry.change_message, "Published on schedule.")
        # Recorded for the editor who scheduled it.
        self.assertEqual(entry.user, self.superuser)
        self.assertEqual(received, [("published", self.superuser)])
        self.assertEqual(
            type(admin_site._registry[Story]).published, [(False, story.pk)]
        )

    def test_runs_once_per_change(self):
        story = Story.objects.create(title="soon")
        self.schedule(story, timezone.now() - datetime.timedelta(minutes=1))

        run_scheduled()
        second = run_scheduled()

        self.assertEqual(second, {"published": 0, "unpublished": 0})
        self.assertEqual(
            LogEntry.objects.filter(change_message="Published on schedule.").count(),
            1,
        )

    def test_published_now_is_not_recorded_again(self):
        story = Story.objects.create(title="draft")
        self.publish(story, "publish")

        self.assertEqual(run_scheduled(), {"published": 0, "unpublished": 0})

    def test_records_expired_content(self):
        story = Story.objects.create(title="live")
        self.publish(story, "publish")
        Story.objects.filter(pk=story.pk).update(
            published_at=NOW - 2 * HOUR,
            unpublish_at=timezone.now() - datetime.timedelta(minutes=1),
        )

        result = run_scheduled()

        self.assertEqual(result, {"published": 0, "unpublished": 1})
        story.refresh_from_db()
        self.assertEqual(story.status, "gone")
        self.assertTrue(
            LogEntry.objects.filter(
                object_id=str(story.pk), change_message="Unpublished on schedule."
            ).exists()
        )

    def test_skips_old_and_trashed_content(self):
        old = Story.objects.create(title="old")
        self.schedule(old, NOW - datetime.timedelta(days=3))
        trashed = Story.objects.create(title="trashed", removed_at=NOW)
        self.schedule(trashed, timezone.now() - datetime.timedelta(minutes=1))

        self.assertEqual(run_scheduled(), {"published": 0, "unpublished": 0})

    def test_content_never_changed_in_the_admin_is_skipped(self):
        Story.objects.create(
            title="code", published_at=timezone.now() - datetime.timedelta(minutes=1)
        )

        self.assertEqual(run_scheduled(), {"published": 0, "unpublished": 0})

    def test_command(self):
        story = Story.objects.create(title="soon")
        self.schedule(story, timezone.now() - datetime.timedelta(minutes=1))

        call_command("content_studio_publish", verbosity=0)

        story.refresh_from_db()
        self.assertEqual(story.status, "live")


class CheckTests(TestCase):
    def studio(self, publishing, model=Story):
        class Studio(ModelStudio):
            pass

        Studio.publishing = publishing
        return Studio(model, admin_site)

    def ids(self, publishing, model=Story):
        return [
            message
            for _id, message in publishing_errors(self.studio(publishing, model))
        ]

    def test_valid_configurations(self):
        self.assertEqual(self.ids(None), [])
        self.assertEqual(self.ids("published_at"), [])
        self.assertEqual(publishing_errors(admin_site._registry[Story]), [])

    def test_wrong_type(self):
        self.assertEqual(len(self.ids(42)), 1)

    def test_unknown_or_wrong_fields(self):
        self.assertIn("is not a field", self.ids("nope")[0])
        self.assertIn("not a DateTimeField", self.ids("title")[0])
        self.assertIn("nullable", self.ids("action_time", model=LogEntry)[0])
        self.assertTrue(
            self.ids(Publishing("published_at", unpublish_at="published_at"))
        )

    def test_status_values(self):
        messages = self.ids(
            Publishing(
                "published_at",
                status="status",
                status_values={"draft": "draft", "live": "live"},
            )
        )

        self.assertTrue(any("unknown state" in message for message in messages))
        self.assertTrue(any("needs a value for published" in m for m in messages))

        messages = self.ids(
            Publishing(
                "published_at",
                status="status",
                status_values={"draft": "draft", "published": "online"},
            )
        )

        self.assertTrue(any("not among the choices" in m for m in messages))
