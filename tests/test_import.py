"""
Tests for import: a studio with import_fields or allow_import creates and
updates objects from a CSV, Excel or JSON file.

Rows go through the edit page's rules (the serializer, the model's
validation, permissions, tenant scoping) and are matched on
import_id_fields, the primary key by default. A preview saves nothing;
an import is all or nothing unless the valid rows are imported on their
own. The "For import" export and the template write what an import
reads back, and large files run as a task when the task backend runs in
the background.
"""

import csv
import datetime
import io
import json
from decimal import Decimal
from unittest import mock, skipIf

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import models as auth_models
from django.core import checks
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, override_settings
from rest_framework.test import APIClient, APIRequestFactory

from content_studio import importing
from content_studio.admin import AdminSerializer, admin_site
from content_studio.checks import check_content_studio
from content_studio.contrib.status.registry import get_task_label
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article, Category, Event, SiteSettings, Venue

EVENTS = "/api/content/testapp.event"
VENUES = "/api/content/testapp.venue"

TENANT_SETTINGS = {
    "ADMIN_SITE": "content_studio.admin.admin_site",
    "TENANT_MODEL": "tests.testapp.models.Category",
}


def studio(model=Event):
    return admin_site._registry[model]


def upload(content, name="import.csv"):
    if isinstance(content, str):
        content = content.encode("utf-8")
    return SimpleUploadedFile(name, content)


def read_csv(response):
    content = b"".join(response.streaming_content).decode("utf-8")
    assert content.startswith("﻿")
    return list(csv.reader(io.StringIO(content[1:])))


def xlsx(rows) -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active

    for row in rows:
        sheet.append(row)

    output = io.BytesIO()
    workbook.save(output)
    return output.getvalue()


class ImportTestCase(TestCase):
    def create_user(self, *permissions, username="staff"):
        user = auth_models.User.objects.create_user(
            username=username, password="x", is_staff=True
        )
        user.user_permissions.set(
            auth_models.Permission.objects.filter(codename__in=permissions)
        )
        return user

    def client_for(self, user):
        client = APIClient()
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
        return client

    def setUp(self):
        self.superuser = auth_models.User.objects.create_superuser(
            username="admin", password="x"
        )
        self.client = self.client_for(self.superuser)
        self.music = Category.objects.create(name="Music")
        self.outdoor = Category.objects.create(name="Outdoor")

    def run_import(self, content, name="import.csv", client=None, url=EVENTS, **data):
        data = {key: "true" if value is True else value for key, value in data.items()}
        return (client or self.client).post(
            url + "/import",
            {"file": upload(content, name), **data},
            format="multipart",
        )

    def result(self, *args, **kwargs):
        response = self.run_import(*args, **kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["result"]


class ConfigurationTests(ImportTestCase):
    def payload(self, model=Event, user=None):
        request = APIRequestFactory().get("/")
        request.user = user or self.superuser
        return AdminSerializer(studio(model)).serialize(request)["list"]["import"]

    def test_studios_opt_in(self):
        self.assertTrue(importing.is_importable(studio(Event)))
        self.assertTrue(importing.is_importable(studio(Venue)))
        self.assertFalse(importing.is_importable(studio(Article)))
        self.assertIsNone(self.payload(Article))

    def test_singletons_are_never_imported(self):
        with mock.patch.object(studio(SiteSettings), "allow_import", True):
            self.assertFalse(importing.is_importable(studio(SiteSettings)))

    def test_payload(self):
        payload = self.payload()

        self.assertEqual(payload["formats"], ["csv", "xlsx", "json"])
        self.assertEqual(payload["template_formats"], ["csv", "xlsx"])
        self.assertEqual(payload["key"], ["id"])
        names = [column["name"] for column in payload["columns"]]
        # The key first; excluded and non-editable fields are left out.
        self.assertEqual(names[0], "id")
        self.assertIn("tags", names)
        self.assertNotIn("secret", names)
        self.assertNotIn("removed_at", names)
        tags = next(c for c in payload["columns"] if c["name"] == "tags")
        self.assertEqual(tags["lookup"], "name")
        title = next(c for c in payload["columns"] if c["name"] == "title")
        self.assertTrue(title["required"])
        self.assertTrue(payload["can_import"])

    def test_import_fields_and_key(self):
        payload = self.payload(Venue)

        self.assertEqual(payload["key"], ["slug"])
        self.assertEqual(
            [column["name"] for column in payload["columns"]],
            ["slug", "name", "kind", "capacity", "opened", "host", "events"],
        )

    def test_permissions(self):
        viewer = self.create_user("view_event", username="viewer")
        changer = self.create_user("view_event", "change_event", username="changer")

        self.assertFalse(self.payload(user=viewer)["can_import"])
        payload = self.payload(user=changer)
        self.assertTrue(payload["can_import"])
        self.assertFalse(payload["can_create"])
        self.assertTrue(payload["can_update"])


class ExportForImportTests(ImportTestCase):
    def test_template(self):
        response = self.client.get(
            EVENTS + "/export", {"export_mode": "template", "export_format": "csv"}
        )

        self.assertEqual(response.status_code, 200)
        self.assertIn("events-import-template.csv", response["Content-Disposition"])
        rows = read_csv(response)
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0][0], "id")
        self.assertIn("title", rows[0])

    def test_excel_template(self):
        from openpyxl import load_workbook

        response = self.client.get(
            EVENTS + "/export", {"export_mode": "template", "export_format": "xlsx"}
        )
        sheet = load_workbook(io.BytesIO(response.content)).active

        self.assertEqual(sheet.max_row, 1)
        self.assertEqual(sheet.cell(1, 1).value, "id")

    def test_no_json_template(self):
        response = self.client.get(
            EVENTS + "/export", {"export_mode": "template", "export_format": "json"}
        )

        self.assertEqual(response.status_code, 400)

    def test_raw_values(self):
        event = Event.objects.create(
            title="=cmd",
            status=Event.Status.CANCELED,
            category=self.music,
            attendees=3,
            is_public=False,
            price=Decimal("9.50"),
            day=datetime.date(2026, 5, 1),
            keywords=["a", "b"],
            details={"x": 1},
            notes="<p>Hi</p>",
        )
        event.tags.set([self.music, self.outdoor])

        response = self.client.get(
            EVENTS + "/export", {"export_mode": "import", "export_format": "csv"}
        )
        header, row = read_csv(response)
        values = dict(zip(header, row))

        self.assertEqual(values["id"], str(event.pk))
        # Formulas are escaped in CSV; the import strips the apostrophe.
        self.assertEqual(values["title"], "'=cmd")
        self.assertEqual(values["status"], "canceled")
        self.assertEqual(values["category"], str(self.music.pk))
        self.assertEqual(values["tags"], "Music, Outdoor")
        self.assertEqual(values["is_public"], "false")
        self.assertEqual(values["price"], "9.50")
        self.assertEqual(values["day"], "2026-05-01")
        self.assertEqual(values["keywords"], "a, b")
        self.assertEqual(json.loads(values["details"]), {"x": 1})
        self.assertEqual(values["notes"], "<p>Hi</p>")

    def test_json(self):
        event = Event.objects.create(title="Gig", keywords=["a"])
        event.tags.set([self.music])

        response = self.client.get(
            EVENTS + "/export", {"export_mode": "import", "export_format": "json"}
        )
        data = json.loads(b"".join(response.streaming_content))

        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["id"], event.pk)
        self.assertEqual(data[0]["tags"], ["Music"])
        self.assertEqual(data[0]["keywords"], ["a"])
        self.assertIs(data[0]["is_public"], True)

    def test_follows_the_list_filters(self):
        Event.objects.create(title="Planned")
        Event.objects.create(title="Canceled", status=Event.Status.CANCELED)

        response = self.client.get(
            EVENTS + "/export",
            {"export_mode": "import", "export_format": "csv", "status": "canceled"},
        )
        rows = read_csv(response)

        self.assertEqual([row[1] for row in rows[1:]], ["Canceled"])

    def test_only_for_importable_studios(self):
        response = self.client.get(
            "/api/content/testapp.article/export", {"export_mode": "import"}
        )

        self.assertEqual(response.status_code, 404)

    def test_round_trip_leaves_everything_unchanged(self):
        for title in ("One", "Two"):
            event = Event.objects.create(
                title=title,
                category=self.music,
                price=Decimal("5.00"),
                day=datetime.date(2026, 1, 2),
                keywords=["x, y", "z"],
                details={"a": [1, 2]},
            )
            event.tags.set([self.outdoor])

        for export_format in ("csv", "xlsx", "json"):
            response = self.client.get(
                EVENTS + "/export",
                {"export_mode": "import", "export_format": export_format},
            )
            content = (
                response.content
                if export_format == "xlsx"
                else b"".join(response.streaming_content)
            )
            result = self.result(content, name=f"events.{export_format}")

            self.assertEqual(result["failed"], 0, (export_format, result))
            self.assertEqual(result["unchanged"], 2, (export_format, result))


class PreviewAndRunTests(ImportTestCase):
    def setUp(self):
        super().setUp()
        self.event = Event.objects.create(title="Gig", attendees=1)

    def file(self):
        return (
            "id,title,status,tags,attendees\n"
            f"{self.event.pk},Gig,Canceled,Music,1\n"
            ',New,planned,"Music, Outdoor",5\n'
            ",Broken,planned,,many\n"
        )

    def test_preview_saves_nothing(self):
        result = self.result(self.file(), preview=True)

        self.assertTrue(result["preview"])
        self.assertFalse(result["applied"])
        self.assertEqual(
            (result["created"], result["updated"], result["failed"]), (1, 1, 1)
        )
        self.assertEqual(Event.objects.count(), 1)
        self.assertEqual(Event.objects.get().status, Event.Status.PLANNED)
        self.assertFalse(LogEntry.objects.exists())

    def test_failures_name_the_row_and_column(self):
        result = self.result(self.file(), preview=True)

        self.assertEqual(result["failures"][0]["row"], 4)
        error = result["failures"][0]["errors"][0]
        self.assertEqual(error["column"], "attendees")
        self.assertTrue(error["messages"])

    def test_a_failing_row_rolls_back_the_import(self):
        result = self.result(self.file())

        self.assertFalse(result["applied"])
        self.assertEqual(Event.objects.count(), 1)
        self.assertFalse(LogEntry.objects.exists())

    def test_skip_errors_imports_the_valid_rows(self):
        result = self.result(self.file(), skip_errors=True)

        self.assertTrue(result["applied"])
        self.assertEqual(Event.objects.count(), 2)
        self.event.refresh_from_db()
        self.assertEqual(self.event.status, Event.Status.CANCELED)
        new = Event.objects.get(title="New")
        self.assertEqual(new.attendees, 5)
        self.assertEqual(
            set(new.tags.values_list("name", flat=True)), {"Music", "Outdoor"}
        )
        # Logged like a save in the admin.
        self.assertEqual(
            set(LogEntry.objects.values_list("action_flag", flat=True)),
            {ADDITION, CHANGE},
        )

    def test_unchanged_rows_are_not_saved(self):
        result = self.result(f"id,title,attendees\n{self.event.pk},Gig,1\n")

        self.assertEqual(result["unchanged"], 1)
        self.assertFalse(LogEntry.objects.exists())

    def test_updates_only_set_the_columns_in_the_file(self):
        Event.objects.filter(pk=self.event.pk).update(status=Event.Status.CANCELED)

        self.result(f"id,attendees\n{self.event.pk},7\n")

        self.event.refresh_from_db()
        self.assertEqual(self.event.attendees, 7)
        self.assertEqual(self.event.status, Event.Status.CANCELED)

    def test_creates_need_the_required_fields(self):
        result = self.result("id,attendees\n,7\n", preview=True)

        self.assertEqual(result["failed"], 1)
        self.assertEqual(result["failures"][0]["errors"][0]["field"], "title")

    def test_unknown_ids_fail(self):
        result = self.result("id,title\n999,Ghost\n", preview=True)

        self.assertEqual(result["failed"], 1)
        self.assertIn("999", result["failures"][0]["errors"][0]["messages"][0])

    def test_trashed_objects_are_not_matched(self):
        Event.objects.filter(pk=self.event.pk).update(
            removed_at=datetime.datetime(2026, 1, 1, tzinfo=datetime.timezone.utc)
        )

        result = self.result(f"id,title\n{self.event.pk},Back\n", preview=True)

        self.assertEqual(result["failed"], 1)

    def test_ignored_columns_are_reported(self):
        result = self.result("title,secret,unknown\nGig 2,x,y\n", preview=True)

        self.assertEqual(result["ignored_columns"], ["secret", "unknown"])
        self.assertEqual(result["created"], 1)

    def test_a_file_without_known_columns_cannot_be_imported(self):
        result = self.result("foo,bar\n1,2\n", preview=True)

        self.assertTrue(result["errors"])
        self.assertEqual(result["failed"], 1)


class ValueTests(ImportTestCase):
    def import_one(self, header, value, **kwargs):
        result = self.result(f"title,{header}\nGig,{value}\n", **kwargs)
        self.assertEqual(result["failed"], 0, result)
        return Event.objects.get(title="Gig")

    def test_choices_by_value_or_label(self):
        self.assertEqual(self.import_one("status", "Canceled").status, "canceled")

    def test_booleans(self):
        for value, expected in (("no", False), ("Yes", True), ("0", False)):
            Event.objects.all().delete()
            self.assertIs(self.import_one("is_public", value).is_public, expected)

    def test_bad_booleans_fail(self):
        result = self.result("title,is_public\nGig,maybe\n", preview=True)

        self.assertEqual(result["failures"][0]["errors"][0]["column"], "is_public")

    def test_headers_may_be_verbose_names(self):
        self.assertEqual(self.import_one("Attendees", "4").attendees, 4)

    def test_formula_escape_is_removed(self):
        result = self.result("title\n'=cmd\n")

        self.assertEqual(result["created"], 1)
        self.assertTrue(Event.objects.filter(title="=cmd").exists())

    def test_json_cells(self):
        event = self.import_one("details", '"{""a"": 1}"')

        self.assertEqual(event.details, {"a": 1})

    def test_invalid_json_cells_fail(self):
        result = self.result("title,details\nGig,{oops\n", preview=True)

        self.assertEqual(result["failures"][0]["errors"][0]["column"], "details")

    def test_tag_lists(self):
        self.assertEqual(self.import_one("keywords", '"a, b"').keywords, ["a", "b"])

    def test_relations_by_lookup(self):
        event = self.import_one("tags", '"Music, Outdoor"')

        self.assertEqual(event.tags.count(), 2)

    def test_unknown_lookups_fail(self):
        result = self.result("title,tags\nGig,Jazz\n", preview=True)
        error = result["failures"][0]["errors"][0]

        self.assertEqual(error["column"], "tags")
        self.assertIn("Jazz", error["messages"][0])

    def test_ambiguous_lookups_fail(self):
        Category.objects.create(name="Music")

        result = self.result("title,tags\nGig,Music\n", preview=True)

        self.assertIn(
            "More than one", result["failures"][0]["errors"][0]["messages"][0]
        )

    def test_relations_by_primary_key(self):
        event = self.import_one("category", str(self.outdoor.pk))

        self.assertEqual(event.category, self.outdoor)

    def test_semicolon_csv(self):
        self.result("title;attendees\nGig;3\n")

        self.assertEqual(Event.objects.get().attendees, 3)

    def test_excel(self):
        content = xlsx(
            [
                ["title", "attendees", "is_public", "day", "starts_at"],
                [
                    "Gig",
                    3,
                    False,
                    datetime.date(2026, 2, 3),
                    datetime.datetime(2026, 2, 3, 20, 0),
                ],
                [None, None, None, None, None],
            ]
        )

        result = self.result(content, name="events.xlsx")

        self.assertEqual(result["created"], 1)
        event = Event.objects.get()
        self.assertEqual(event.attendees, 3)
        self.assertFalse(event.is_public)
        self.assertEqual(event.day, datetime.date(2026, 2, 3))
        self.assertIsNotNone(event.starts_at)

    def test_json_file(self):
        content = json.dumps(
            [{"title": "Gig", "tags": ["Music"], "details": {"a": 1}, "attendees": 2}]
        )

        self.result(content, name="events.json")

        event = Event.objects.get()
        self.assertEqual(event.details, {"a": 1})
        self.assertEqual(list(event.tags.all()), [self.music])

    def test_unreadable_files(self):
        for content, name in (
            ("{", "events.json"),
            ('{"a": 1}', "events.json"),
            ("nope", "events.xlsx"),
            ("title\nGig\n", "events.txt.exe"),
        ):
            response = self.run_import(content, name=name)

            self.assertEqual(response.status_code, 400, name)
            self.assertIn("file", response.json())


class CustomKeyTests(ImportTestCase):
    def test_rows_without_a_match_are_created_and_matches_updated(self):
        Venue.objects.create(name="Old", slug="paradiso")
        Event.objects.create(title="Gig")

        result = self.result(
            "slug,name,kind,host,events\n"
            "paradiso,Paradiso,Club,admin,Gig\n"
            "melkweg,Melkweg,hall,,\n",
            url=VENUES,
        )

        self.assertEqual((result["created"], result["updated"]), (1, 1))
        paradiso = Venue.objects.get(slug="paradiso")
        self.assertEqual(paradiso.name, "Paradiso")
        self.assertEqual(paradiso.kind, "club")
        self.assertEqual(paradiso.host, self.superuser)
        self.assertEqual(paradiso.events.get().title, "Gig")

    def test_the_key_column_is_required(self):
        result = self.result("name\nParadiso\n", url=VENUES, preview=True)

        self.assertIn("slug", result["errors"][0])

    def test_model_validation_runs(self):
        result = self.result("slug,name,capacity\nx,X,13\n", url=VENUES, preview=True)

        self.assertEqual(
            result["failures"][0]["errors"][0],
            {
                "column": "capacity",
                "field": "capacity",
                "messages": ["Unlucky capacity."],
            },
        )


class PermissionTests(ImportTestCase):
    def test_viewers_cannot_import(self):
        viewer = self.client_for(self.create_user("view_event", username="viewer"))

        response = self.run_import("title\nGig\n", client=viewer)

        self.assertEqual(response.status_code, 403)

    def test_rows_need_the_permission_they_use(self):
        event = Event.objects.create(title="Gig")
        changer = self.client_for(
            self.create_user("view_event", "change_event", username="changer")
        )

        result = self.result(
            f"id,title\n{event.pk},Gig 2\n,New\n", client=changer, skip_errors=True
        )

        self.assertEqual((result["updated"], result["failed"]), (1, 1))
        self.assertFalse(Event.objects.filter(title="New").exists())

    def test_only_importable_studios(self):
        response = self.run_import("title\nx\n", url="/api/content/testapp.article")

        self.assertEqual(response.status_code, 404)

    def test_tenant_scoping(self):
        theirs = Event.objects.create(title="Theirs", category=self.outdoor)

        with override_settings(CONTENT_STUDIO=TENANT_SETTINGS):
            response = self.client.post(
                EVENTS + "/import",
                {
                    "file": upload(f"id,title\n{theirs.pk},Mine\n,New\n"),
                    "skip_errors": "true",
                },
                format="multipart",
                HTTP_X_DCS_TENANT=str(self.music.pk),
            )

        result = response.json()["result"]
        self.assertEqual((result["created"], result["failed"]), (1, 1))
        self.assertEqual(Event.objects.get(title="New").category, self.music)
        theirs.refresh_from_db()
        self.assertEqual(theirs.title, "Theirs")


class LimitTests(ImportTestCase):
    def test_too_many_rows_in_the_request(self):
        with mock.patch.object(cs_settings, "IMPORT_MAX_ROWS", 2):
            response = self.run_import("title\na\nb\nc\n")

        self.assertEqual(response.status_code, 400)
        self.assertIn("at most", response.json()["file"][0])

    def test_too_large_files(self):
        with mock.patch.object(cs_settings, "UPLOAD_MAX_SIZE", 5):
            response = self.run_import("title\nGig\n")

        self.assertEqual(response.status_code, 400)


@skipIf(importing.run_import_task is None, "Django tasks is not installed")
@override_settings(
    TASKS={"default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}}
)
class BackgroundTests(ImportTestCase):
    """With a background backend, large files run as a task. The
    immediate backend runs it in place, once the request commits."""

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(importing, "runs_in_background", return_value=True)
        patcher.start()
        self.addCleanup(patcher.stop)
        settings_patcher = mock.patch.object(cs_settings, "IMPORT_TASK_ROWS", 2)
        settings_patcher.start()
        self.addCleanup(settings_patcher.stop)

    def start(self, **data):
        with self.captureOnCommitCallbacks(execute=True):
            response = self.run_import("title\na\nb\n,\n", **data)

        self.assertEqual(response.status_code, 202, response.content)
        return response.json()["job"]

    def status(self, job, client=None):
        return (client or self.client).get(f"{EVENTS}/import/{job['id']}")

    def test_preview_then_import(self):
        job = self.start(preview=True)
        self.assertEqual(job["status"], "queued")

        state = self.status(job).json()["job"]
        self.assertEqual(state["status"], "done")
        self.assertEqual(state["result"]["created"], 2)
        self.assertEqual(Event.objects.count(), 0)

        with self.captureOnCommitCallbacks(execute=True):
            response = self.client.post(
                EVENTS + "/import", {"job": job["id"]}, format="multipart"
            )

        self.assertEqual(response.status_code, 202)
        state = self.status(job).json()["job"]
        self.assertEqual(state["status"], "done")
        self.assertTrue(state["result"]["applied"])
        self.assertEqual(Event.objects.count(), 2)
        self.assertEqual(LogEntry.objects.count(), 2)

    def test_jobs_are_private(self):
        job = self.start(preview=True)
        other = self.client_for(
            self.create_user("view_event", "add_event", username="other")
        )

        self.assertEqual(self.status(job, client=other).status_code, 404)

    def test_unknown_jobs(self):
        response = self.client.get(f"{EVENTS}/import/not-a-job")

        self.assertEqual(response.status_code, 404)

    def test_small_files_run_in_the_request(self):
        response = self.run_import("title\na\n")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(Event.objects.count(), 1)

    def test_only_a_previewed_job_can_be_imported(self):
        job = self.start()

        response = self.client.post(
            EVENTS + "/import", {"job": job["id"]}, format="multipart"
        )

        self.assertEqual(response.status_code, 400)


@skipIf(importing.run_import_task is None, "Django tasks is not installed")
class BackgroundDetectionTests(TestCase):
    @override_settings(
        TASKS={
            "default": {"BACKEND": "django.tasks.backends.immediate.ImmediateBackend"}
        }
    )
    def test_the_immediate_backend_runs_in_the_request(self):
        self.assertFalse(importing.runs_in_background())

    @override_settings(
        TASKS={"default": {"BACKEND": "django.tasks.backends.dummy.DummyBackend"}}
    )
    def test_the_dummy_backend_never_runs_tasks(self):
        self.assertFalse(importing.runs_in_background())


class StatusPageTests(TestCase):
    def test_the_status_page_names_the_import_task(self):
        path = "content_studio.importing.run_import"

        self.assertEqual(str(get_task_label(path)), "Import from a file")
        if importing.run_import_task is not None:
            self.assertEqual(importing.run_import_task.module_path, path)


class ImportCheckTests(TestCase):
    def messages(self, check_id):
        return [m for m in check_content_studio() if m.id == check_id]

    def test_valid_configuration_passes(self):
        self.assertEqual(self.messages("content_studio.E048"), [])
        self.assertEqual(self.messages("content_studio.W026"), [])

    def test_import_fields_must_be_writable_model_fields(self):
        with mock.patch.object(
            studio(), "import_fields", ["title", "nope", "title", "secret", "id"]
        ):
            messages = [m.msg for m in self.messages("content_studio.E048")]

        self.assertEqual(len(messages), 4, messages)
        self.assertIn("'nope'", messages[0])
        self.assertIn("more than once", messages[1])
        self.assertIn("edit page", messages[2])
        self.assertIn("primary key", messages[3])

    def test_import_fields_must_be_a_list(self):
        with mock.patch.object(studio(), "import_fields", "title"):
            messages = self.messages("content_studio.E048")

        self.assertEqual(len(messages), 1)
        self.assertIsInstance(messages[0], checks.Error)

    def test_id_fields_must_be_import_fields(self):
        with mock.patch.object(studio(Venue), "import_id_fields", ["capacity", "x"]):
            with mock.patch.object(studio(Venue), "import_fields", ["name"]):
                messages = [m.msg for m in self.messages("content_studio.E048")]

        self.assertEqual(len(messages), 2, messages)

    def test_lookups_must_name_related_fields(self):
        with mock.patch.object(
            studio(), "import_lookups", {"title": "x", "tags": "nope"}
        ):
            messages = [m.msg for m in self.messages("content_studio.E048")]

        self.assertEqual(len(messages), 2, messages)

    def test_non_unique_keys_warn(self):
        with mock.patch.object(studio(Venue), "import_id_fields", ["name"]):
            with mock.patch.object(studio(Venue), "import_fields", ["name", "slug"]):
                messages = self.messages("content_studio.W026")

        self.assertEqual(len(messages), 1)

    def test_singletons_warn(self):
        with mock.patch.object(studio(SiteSettings), "allow_import", True):
            messages = self.messages("content_studio.W026")

        self.assertEqual(len(messages), 1)
