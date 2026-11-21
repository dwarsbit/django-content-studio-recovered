"""
Tests for previews and shared draft links (content_studio.previews).

Bulletin has publishing on published_at; its page URL comes from a
patched get_absolute_url.
"""

import datetime
from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import models as auth_models
from django.core import signing
from django.core.management import call_command
from django.http import HttpResponse
from django.template import Context, Template
from django.test import RequestFactory, TestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import admin_site
from content_studio.checks import preview_errors, preview_middleware_warnings
from content_studio.previews import (
    SHARED,
    STAFF,
    get_preview,
    hash_key,
    make_staff_token,
    preview_url,
    previewable,
    with_token,
)
from content_studio.previews.middleware import PreviewMiddleware
from content_studio.previews.models import PreviewLink
from content_studio.previews.permissions import create_permissions
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Bulletin, Note

NOW = timezone.now()
HOUR = datetime.timedelta(hours=1)
DAY = datetime.timedelta(days=1)


def page(self):
    return f"/bulletins/{self.pk}/"


class PreviewTestCase(TestCase):
    def setUp(self):
        patcher = mock.patch.object(Bulletin, "get_absolute_url", page, create=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.superuser = auth_models.User.objects.create_superuser(
            username="admin", password="x", first_name="Alex", last_name="Morgan"
        )
        self.client = self.client_for(self.superuser)
        self.studio = admin_site._registry[Bulletin]
        self.factory = RequestFactory()
        self.draft = Bulletin.objects.create(title="draft")
        self.live = Bulletin.objects.create(title="live", published_at=NOW - HOUR)

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def staff(self, *codenames, username="staff"):
        create_permissions()
        user = auth_models.User.objects.create_user(
            username=username, password="x", is_staff=True
        )
        user.user_permissions.set(
            auth_models.Permission.objects.filter(codename__in=codenames)
        )
        return user

    def site_request(self, token=None):
        return self.factory.get("/bulletins/", {"preview": token} if token else {})

    def share(self, obj=None, client=None, **data):
        return (client or self.client).post(
            f"/api/content/testapp.bulletin/{(obj or self.draft).pk}/preview-links",
            data,
            format="json",
        )


class DetailTests(PreviewTestCase):
    def test_draft_keeps_its_page_url_and_says_it_is_not_live(self):
        data = self.client.get(f"/api/content/testapp.bulletin/{self.draft.pk}").json()

        self.assertEqual(data["__view_on_site__"], f"/bulletins/{self.draft.pk}/")
        self.assertEqual(data["__preview__"], {"live": False, "can_share": True})

    def test_live_object(self):
        data = self.client.get(f"/api/content/testapp.bulletin/{self.live.pk}").json()

        self.assertEqual(data["__preview__"], {"live": True, "can_share": False})

    def test_no_preview_without_publishing(self):
        note = Note.objects.create(title="n")
        data = self.client.get(f"/api/content/testapp.note/{note.pk}").json()

        self.assertIsNone(data["__preview__"])

    def test_preview_false_turns_it_off(self):
        with mock.patch.object(self.studio, "preview", False):
            data = self.client.get(
                f"/api/content/testapp.bulletin/{self.draft.pk}"
            ).json()

        self.assertIsNone(data["__preview__"])
        self.assertIsNone(data["__view_on_site__"])

    def test_can_share_needs_the_share_permission(self):
        viewer = self.staff("view_bulletin")
        sharer = self.staff("view_bulletin", "share_bulletin", username="sharer")
        url = f"/api/content/testapp.bulletin/{self.draft.pk}"

        self.assertFalse(
            self.client_for(viewer).get(url).json()["__preview__"]["can_share"]
        )
        self.assertTrue(
            self.client_for(sharer).get(url).json()["__preview__"]["can_share"]
        )


class StaffPreviewTests(PreviewTestCase):
    def test_draft_gets_a_staff_token(self):
        response = self.client.post(
            f"/api/content/testapp.bulletin/{self.draft.pk}/preview", {}, format="json"
        )

        self.assertEqual(response.status_code, 200)
        url = response.json()["url"]
        self.assertTrue(url.startswith(f"/bulletins/{self.draft.pk}/?preview="))

        token = url.split("preview=", 1)[1]
        preview = get_preview(self.site_request(signing_unquote(token)))
        self.assertEqual(preview.kind, STAFF)
        self.assertEqual(preview.pk, str(self.draft.pk))
        self.assertEqual(preview.user, self.superuser)
        self.assertGreater(
            preview.expires_at, timezone.now() + 50 * datetime.timedelta(minutes=1)
        )

    def test_live_object_gets_its_plain_url(self):
        response = self.client.post(
            f"/api/content/testapp.bulletin/{self.live.pk}/preview", {}, format="json"
        )

        self.assertEqual(response.json()["url"], f"/bulletins/{self.live.pk}/")

    def test_no_page_url_is_not_found(self):
        with mock.patch.object(self.studio, "get_link_url", return_value=None):
            response = self.client.post(
                f"/api/content/testapp.bulletin/{self.draft.pk}/preview",
                {},
                format="json",
            )

        self.assertEqual(response.status_code, 404)

    def test_needs_view_permission(self):
        nobody = self.staff()
        response = self.client_for(nobody).post(
            f"/api/content/testapp.bulletin/{self.draft.pk}/preview", {}, format="json"
        )

        self.assertEqual(response.status_code, 403)

    def test_expired_token_does_not_work(self):
        token = make_staff_token(self.superuser, self.draft)

        with override_settings(CONTENT_STUDIO={"PREVIEW_MAX_AGE": 60}):
            with mock.patch("django.core.signing.time.time", return_value=9e12):
                self.assertIsNone(get_preview(self.site_request(token)))

    def test_tampered_token_does_not_work(self):
        token = make_staff_token(self.superuser, self.draft)

        self.assertIsNone(get_preview(self.site_request(token[:-2] + "xx")))

    def test_editor_who_lost_view_permission(self):
        editor = self.staff("view_bulletin", username="editor")
        token = make_staff_token(editor, self.draft)
        self.assertIsNotNone(get_preview(self.site_request(token)))

        editor.user_permissions.clear()
        editor = auth_models.User.objects.get(pk=editor.pk)  # drop the perm cache
        self.assertIsNone(get_preview(self.site_request(token)))

    def test_inactive_editor(self):
        token = make_staff_token(self.superuser, self.draft)
        auth_models.User.objects.filter(pk=self.superuser.pk).update(is_active=False)

        self.assertIsNone(get_preview(self.site_request(token)))

    def test_preview_url_helper(self):
        url = preview_url(self.studio, self.draft, self.superuser)

        self.assertIn("preview=", url)
        self.assertEqual(
            preview_url(self.studio, self.live, self.superuser),
            f"/bulletins/{self.live.pk}/",
        )


def signing_unquote(value):
    from urllib.parse import unquote

    return unquote(value)


class PreviewableTests(PreviewTestCase):
    def test_without_token_only_live_objects(self):
        objects = previewable(self.site_request(), Bulletin.objects.all())

        self.assertEqual(list(objects), [self.live])

    def test_staff_token_adds_the_draft(self):
        token = make_staff_token(self.superuser, self.draft)
        objects = previewable(self.site_request(token), Bulletin.objects.all())

        self.assertEqual(set(objects), {self.live, self.draft})

    def test_token_for_another_model_adds_nothing(self):
        note = Note.objects.create(title="n")
        token = signing.dumps(
            {"m": "testapp.note", "p": str(note.pk), "l": None, "u": self.superuser.pk},
            salt="content_studio.previews.staff",
            compress=True,
        )
        objects = previewable(self.site_request(token), Bulletin.objects.all())

        self.assertEqual(list(objects), [self.live])

    def test_other_draft_stays_hidden(self):
        other = Bulletin.objects.create(title="other draft")
        token = make_staff_token(self.superuser, self.draft)
        objects = previewable(self.site_request(token), Bulletin.objects.all())

        self.assertNotIn(other, objects)

    def test_model_without_publishing_is_returned_as_is(self):
        Note.objects.create(title="n")
        queryset = Note.objects.all()

        self.assertIs(previewable(self.site_request(), queryset), queryset)


class SharedLinkTests(PreviewTestCase):
    def test_share_returns_the_url_once(self):
        expires = (timezone.now() + 7 * DAY).isoformat()
        response = self.share(expires_at=expires, note="For the client")

        self.assertEqual(response.status_code, 201, response.content)
        created = response.json()["created"]
        self.assertTrue(created["url"].startswith(f"/bulletins/{self.draft.pk}/?"))
        self.assertEqual(created["note"], "For the client")
        self.assertEqual(created["created_by"], "Alex Morgan")
        self.assertEqual(len(response.json()["links"]), 1)
        self.assertNotIn("url", response.json()["links"][0])

        key = created["url"].split("preview=", 1)[1]
        link = PreviewLink.objects.get()
        self.assertEqual(link.key_hash, hash_key(key))
        self.assertNotEqual(link.key_hash, key)

    def test_shared_link_opens_the_draft_and_counts(self):
        url = self.share().json()["created"]["url"]
        key = url.split("preview=", 1)[1]

        request = self.site_request(key)
        objects = previewable(request, Bulletin.objects.all())
        self.assertIn(self.draft, objects)
        preview = get_preview(request)
        self.assertEqual(preview.kind, SHARED)
        self.assertEqual(preview.shared_by, "Alex Morgan")
        get_preview(request)  # once per request

        link = PreviewLink.objects.get()
        self.assertEqual(link.opens, 1)
        self.assertIsNotNone(link.last_opened_at)

    def test_a_week_by_default(self):
        self.share()

        expires_at = PreviewLink.objects.get().expires_at
        self.assertAlmostEqual(
            expires_at.timestamp(), (timezone.now() + 7 * DAY).timestamp(), delta=60
        )

    def test_no_expiry(self):
        response = self.share(expires_at=None)

        self.assertIsNone(response.json()["created"]["expires_at"])
        self.assertIsNone(PreviewLink.objects.get().expires_at)

    def test_expired_link_stops(self):
        url = self.share().json()["created"]["url"]
        PreviewLink.objects.update(expires_at=timezone.now() - HOUR)

        self.assertIsNone(get_preview(self.site_request(url.split("preview=")[1])))
        self.assertEqual(
            self.client.get(
                f"/api/content/testapp.bulletin/{self.draft.pk}/preview-links"
            ).json()["links"],
            [],
        )

    def test_past_expiry_is_refused(self):
        response = self.share(expires_at=(timezone.now() - HOUR).isoformat())

        self.assertEqual(response.status_code, 400)
        self.assertIn("expires_at", response.json())

    def test_revoke(self):
        url = self.share().json()["created"]["url"]
        link = PreviewLink.objects.get()

        response = self.client.delete(
            f"/api/content/testapp.bulletin/{self.draft.pk}/preview-links/{link.pk}"
        )

        self.assertEqual(response.status_code, 204)
        self.assertFalse(PreviewLink.objects.exists())
        self.assertIsNone(get_preview(self.site_request(url.split("preview=")[1])))

    def test_revoke_only_the_objects_links(self):
        self.share()
        link = PreviewLink.objects.get()

        response = self.client.delete(
            f"/api/content/testapp.bulletin/{self.live.pk}/preview-links/{link.pk}"
        )

        self.assertEqual(response.status_code, 404)
        self.assertTrue(PreviewLink.objects.exists())

    def test_live_content_is_not_shared(self):
        response = self.share(obj=self.live)

        self.assertEqual(response.status_code, 400)
        self.assertFalse(PreviewLink.objects.exists())

    def test_needs_the_share_permission(self):
        viewer = self.staff("view_bulletin", "change_bulletin")
        sharer = self.staff("view_bulletin", "share_bulletin", username="sharer")

        self.assertEqual(self.share(client=self.client_for(viewer)).status_code, 403)
        self.assertEqual(
            self.client_for(viewer)
            .get(f"/api/content/testapp.bulletin/{self.draft.pk}/preview-links")
            .status_code,
            403,
        )
        self.assertEqual(self.share(client=self.client_for(sharer)).status_code, 201)

    def test_sharing_and_revoking_are_logged(self):
        self.share()
        link = PreviewLink.objects.get()
        self.client.delete(
            f"/api/content/testapp.bulletin/{self.draft.pk}/preview-links/{link.pk}"
        )

        messages = list(
            LogEntry.objects.filter(object_id=str(self.draft.pk))
            .order_by("pk")
            .values_list("change_message", flat=True)
        )
        self.assertEqual(messages, ["Shared a draft link.", "Revoked a draft link."])

    def test_link_of_a_published_draft_shows_the_live_page(self):
        url = self.share().json()["created"]["url"]
        Bulletin.objects.filter(pk=self.draft.pk).update(published_at=NOW - HOUR)

        request = self.site_request(url.split("preview=")[1])
        self.assertIn(self.draft, previewable(request, Bulletin.objects.all()))

    def test_prune_command(self):
        self.share()
        self.share(expires_at=None)
        PreviewLink.objects.filter(expires_at__isnull=False).update(
            expires_at=timezone.now() - HOUR
        )

        call_command("content_studio_prune_previews", stdout=mock.MagicMock())

        self.assertEqual(PreviewLink.objects.count(), 1)


class SiteTests(PreviewTestCase):
    def test_middleware_keeps_preview_pages_private(self):
        middleware = PreviewMiddleware(lambda request: HttpResponse("ok"))

        response = middleware(self.site_request("anything"))
        self.assertIn("no-store", response["Cache-Control"])
        self.assertIn("private", response["Cache-Control"])
        self.assertEqual(response["X-Robots-Tag"], "noindex, nofollow")
        self.assertEqual(response["Referrer-Policy"], "no-referrer")

        plain = middleware(self.site_request())
        self.assertNotIn("X-Robots-Tag", plain)

    def render_banner(self, request):
        return Template("{% load content_studio %}{% preview_banner %}").render(
            Context({"request": request})
        )

    def test_banner_for_a_staff_preview(self):
        token = make_staff_token(self.superuser, self.draft)
        html = self.render_banner(self.site_request(token))

        self.assertIn("Draft preview", html)
        self.assertIn("This link stops working at", html)
        self.assertIn(f"content/testapp.bulletin/{self.draft.pk}", html)

    def test_banner_for_a_shared_link(self):
        url = self.share(expires_at=None).json()["created"]["url"]
        html = self.render_banner(self.site_request(url.split("preview=")[1]))

        self.assertIn("Shared by Alex Morgan", html)
        self.assertNotIn("content/testapp.bulletin", html)

    def test_no_banner_without_token_or_on_live_pages(self):
        self.assertEqual(self.render_banner(self.site_request()), "")
        token = make_staff_token(self.superuser, self.live)
        self.assertEqual(self.render_banner(self.site_request(token)), "")

    def test_with_token_replaces_the_parameter(self):
        self.assertEqual(
            with_token("/a/?x=1&preview=old", "new"), "/a/?x=1&preview=new"
        )


class CheckTests(PreviewTestCase):
    def test_preview_must_be_a_boolean(self):
        with mock.patch.object(self.studio, "preview", "yes"):
            self.assertEqual(preview_errors(self.studio)[0][0], "content_studio.E056")

        self.assertEqual(preview_errors(self.studio), [])

    def test_middleware_warning(self):
        self.assertEqual(preview_middleware_warnings(), [])

        with self.settings(MIDDLEWARE=[]):
            self.assertEqual(preview_middleware_warnings()[0][0], "content_studio.W031")

    def test_share_permission_is_created(self):
        create_permissions()

        self.assertTrue(
            auth_models.Permission.objects.filter(
                codename="share_bulletin", name="Can share bulletin"
            ).exists()
        )
        self.assertFalse(
            auth_models.Permission.objects.filter(codename="share_note").exists()
        )
