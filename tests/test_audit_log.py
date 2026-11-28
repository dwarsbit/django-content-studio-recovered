"""
Audit log (content_studio.contrib.audit_log): sign-in events, the action
kept with each activity log entry, the page's API and export, pruning
and the check.
"""

import csv
import datetime
import io
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import authenticate
from django.contrib.auth import models as auth_models
from django.contrib.contenttypes.models import ContentType
from django.core.management import call_command
from django.test import RequestFactory, override_settings
from django.urls import resolve
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import admin_site
from content_studio.checks import audit_log_errors
from content_studio.contrib.audit_log import entries as timeline
from content_studio.contrib.audit_log.models import EntryAction, SignInEvent
from content_studio.contrib.audit_log.recording import describe_user_agent, prune
from content_studio.settings import cs_settings
from content_studio.signals import record_change
from content_studio.throttling import client_ip
from content_studio.token_backends.jwt import REFRESH_COOKIE_NAME
from tests.test_activity import AuthenticatedTestCase
from tests.testapp.models import Article

ARTICLES = "/api/content/testapp.article"
AUDIT_LOG = "/api/audit-log"
LOGIN = "/api/login/usernamepassword"
LOGOUT = "/api/tokens/jsonwebtoken/logout"
FIREFOX = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 14.5; rv:132.0) "
    "Gecko/20100101 Firefox/132.0"
)


class AuditLogTestCase(AuthenticatedTestCase):
    def setUp(self):
        self.superuser = self.create_user(superuser=True, username="root")
        self.client = self.client_for(self.superuser)
        self.editor = auth_models.User.objects.create_user(
            username="maya", password="right-password", is_staff=True
        )

    def login(self, username="maya", password="right-password", **extra):
        return APIClient(REMOTE_ADDR="10.0.0.7", HTTP_USER_AGENT=FIREFOX).post(
            LOGIN, {"username": username, "password": password}, format="json", **extra
        )

    def create_article(self, title="Draft"):
        response = self.client.post(ARTICLES, {"title": title}, format="json")
        self.assertEqual(response.status_code, 201, response.content)
        return Article.objects.get(pk=response.json()["id"])

    def entries(self, **params):
        response = self.client.get(AUDIT_LOG, params)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()


class SignInEventTests(AuditLogTestCase):
    def test_a_sign_in_is_recorded_with_address_and_browser(self):
        response = self.login()

        self.assertEqual(response.status_code, 200, response.content)
        event = SignInEvent.objects.get()
        self.assertEqual(event.kind, SignInEvent.SIGNED_IN)
        self.assertEqual(event.user, self.editor)
        self.assertEqual(event.username, "maya")
        self.assertEqual(event.method, "password")
        self.assertEqual(event.ip_address, "10.0.0.7")
        self.assertEqual(event.user_agent, FIREFOX)

    def test_a_wrong_password_is_a_failed_sign_in_of_the_user(self):
        self.assertEqual(self.login(password="wrong").status_code, 403)

        event = SignInEvent.objects.get()
        self.assertEqual(event.kind, SignInEvent.FAILED)
        self.assertEqual(event.reason, "wrong_password")
        self.assertEqual(event.user, self.editor)

    def test_an_unknown_username_is_kept_as_typed(self):
        self.login(username="nobody", password="wrong")

        event = SignInEvent.objects.get()
        self.assertIsNone(event.user)
        self.assertEqual(event.username, "nobody")

    def test_a_user_who_may_not_sign_in_is_not_allowed(self):
        self.editor.is_staff = False
        self.editor.save()

        self.login()

        event = SignInEvent.objects.get()
        self.assertEqual(event.kind, SignInEvent.FAILED)
        self.assertEqual(event.reason, "not_allowed")

    def test_a_locked_account_is_recorded_as_locked(self):
        with mock.patch(
            "content_studio.login_failures.account_locked", return_value=True
        ):
            self.assertEqual(self.login().status_code, 429)

        self.assertEqual(SignInEvent.objects.get().reason, "locked")

    def test_login_views_stay_out_of_atomic_requests(self):
        # A refused login answers with an error, which rolls back the
        # request's transaction under ATOMIC_REQUESTS: the failed sign-in
        # would go with it.
        for path in (LOGIN, "/api/two-factor/verify"):
            view = resolve(path).func
            self.assertIn("default", getattr(view, "_non_atomic_requests", set()))

    def test_logging_out_is_recorded_once(self):
        login = self.login()
        client = APIClient(REMOTE_ADDR="10.0.0.8")
        client.cookies[REFRESH_COOKIE_NAME] = login.cookies[REFRESH_COOKIE_NAME].value
        client.credentials(HTTP_AUTHORIZATION=f"Bearer {login.json()['access']}")

        self.assertEqual(client.post(LOGOUT).status_code, 204)
        client.post(LOGOUT)

        event = SignInEvent.objects.get(kind=SignInEvent.SIGNED_OUT)
        self.assertEqual(event.user, self.editor)
        self.assertEqual(event.ip_address, "10.0.0.8")

    def test_sign_ins_outside_content_studio_are_not_recorded(self):
        request = RequestFactory().post("/accounts/login/")

        self.assertIsNone(authenticate(request, username="maya", password="wrong"))
        self.assertFalse(SignInEvent.objects.exists())

    def test_a_failing_write_never_breaks_the_sign_in(self):
        with mock.patch.object(
            SignInEvent.objects, "create", side_effect=RuntimeError("down")
        ):
            response = self.login()

        self.assertEqual(response.status_code, 200)


class TwoFactorSignInTests(AuditLogTestCase):
    def setUp(self):
        super().setUp()
        from content_studio.contrib.two_factor import service, totp

        self.totp = totp
        self.secret = totp.generate_secret()
        self.codes = service.enable(self.editor, self.secret, self.code())

    def code(self):
        return self.totp.code_at(self.secret, self.totp.current_step())

    def verify(self, **data):
        challenge = self.login().json()["two_factor"]["challenge"]
        return APIClient(REMOTE_ADDR="10.0.0.7").post(
            "/api/two-factor/verify", {"challenge": challenge, **data}, format="json"
        )

    def test_a_wrong_code_is_a_failed_two_factor_sign_in(self):
        self.verify(code="000000" if self.code() != "000000" else "111111")

        event = SignInEvent.objects.get()
        self.assertEqual(event.kind, SignInEvent.FAILED)
        self.assertEqual(event.method, "two_factor")
        self.assertEqual(event.reason, "wrong_code")

    def test_a_recovery_code_signs_in_with_its_method(self):
        response = self.verify(recovery_code=self.codes[0])

        self.assertEqual(response.status_code, 200, response.content)
        event = SignInEvent.objects.get()
        self.assertEqual(event.kind, SignInEvent.SIGNED_IN)
        self.assertEqual(event.method, "recovery_code")


class EntryActionTests(AuditLogTestCase):
    def test_record_change_keeps_the_action(self):
        article = Article.objects.create(title="Story")
        entry = record_change(
            SimpleNamespace(user=self.superuser), article, "published", "Published."
        )

        self.assertEqual(EntryAction.objects.get(log_entry=entry).action, "published")

        listed = self.entries(action="published")["entries"]
        self.assertEqual([item["entry_id"] for item in listed], [entry.pk])
        self.assertEqual(listed[0]["action"], "published")

    def test_older_entries_go_by_their_flag(self):
        article = Article.objects.create(title="Old")
        LogEntry.objects.create(
            user=self.superuser,
            action_flag=CHANGE,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk,
            object_repr="Old",
        )
        record_change(SimpleNamespace(user=self.superuser), article, "restored")

        updated = self.entries(action="updated")["entries"]
        self.assertEqual([item["action"] for item in updated], ["updated"])
        restored = self.entries(action="restored")["entries"]
        self.assertEqual([item["action"] for item in restored], ["restored"])


class ListTests(AuditLogTestCase):
    def test_changes_and_sign_ins_in_one_timeline(self):
        self.login()
        article = self.create_article("First")

        data = self.entries()

        self.assertEqual(
            [item["kind"] for item in data["entries"]], ["change", "sign_in"]
        )
        change, sign_in = data["entries"]
        self.assertEqual(change["action"], "created")
        self.assertEqual(change["object_id"], str(article.pk))
        self.assertEqual(change["model"], "testapp.article")
        self.assertTrue(change["object_exists"])
        self.assertTrue(change["has_version"])
        self.assertEqual(sign_in["browser"], "Firefox on macOS")
        self.assertEqual(sign_in["ip_address"], "10.0.0.7")
        self.assertIsNone(data["next"])
        self.assertIn(
            {"value": "testapp.article", "label": "article"},
            data["options"]["models"],
        )
        self.assertIn("maya", [user["username"] for user in data["options"]["users"]])

    def test_filters(self):
        self.login()
        self.login(password="wrong")
        article = self.create_article("Findable")

        by_model = self.entries(model="testapp.article")["entries"]
        self.assertEqual([item["kind"] for item in by_model], ["change"])
        by_object = self.entries(model="testapp.article", object=str(article.pk))
        self.assertEqual(len(by_object["entries"]), 1)
        self.assertEqual(self.entries(model="testapp.nothing")["entries"], [])

        by_user = self.entries(user=str(self.editor.pk))["entries"]
        self.assertEqual({item["kind"] for item in by_user}, {"sign_in"})
        self.assertEqual(self.entries(user="not-a-number")["entries"], [])

        failed = self.entries(action="sign_in_failed")["entries"]
        self.assertEqual([item["reason"] for item in failed], ["wrong_password"])

        self.assertEqual(len(self.entries(q="findable")["entries"]), 1)
        self.assertEqual(len(self.entries(q="10.0.0.7")["entries"]), 2)

        tomorrow = (timezone.localdate() + datetime.timedelta(days=1)).isoformat()
        self.assertEqual(self.entries(since=tomorrow)["entries"], [])
        self.assertEqual(
            len(self.entries(until=timezone.localdate().isoformat())["entries"]), 3
        )

    def test_pages_follow_one_another_across_both_sources(self):
        now = timezone.now()
        article = Article.objects.create(title="Paged")
        content_type = ContentType.objects.get_for_model(Article)

        for i in range(60):
            LogEntry.objects.create(
                user=self.superuser,
                action_flag=CHANGE,
                content_type=content_type,
                object_id=article.pk,
                object_repr=f"Paged {i}",
                action_time=now - datetime.timedelta(minutes=i),
            )
            SignInEvent.objects.create(
                kind=SignInEvent.SIGNED_IN,
                user=self.editor,
                username="maya",
                created_at=now - datetime.timedelta(minutes=i),
            )

        seen = []
        page = self.entries()

        while True:
            seen += [item["id"] for item in page["entries"]]
            if not page["next"]:
                break
            page = self.entries(after=page["next"])

        self.assertEqual(len(seen), 120)
        self.assertEqual(len(set(seen)), 120)
        self.assertEqual(seen[:2], [seen[0], seen[1]])
        self.assertTrue(seen[0].startswith("change-"))

    def test_a_bad_cursor_is_refused(self):
        response = self.client.get(AUDIT_LOG, {"after": "garbage"})

        self.assertEqual(response.status_code, 400)

    def test_superusers_only_by_default(self):
        response = self.client_for(self.editor).get(AUDIT_LOG)
        self.assertEqual(response.status_code, 403)

        discover = self.client_for(self.editor).get("/api/discover").json()
        self.assertFalse(discover["audit_log"]["enabled"])
        self.assertTrue(self.client.get("/api/discover").json()["audit_log"]["enabled"])

    def test_the_hook_lets_others_in_with_the_models_they_may_view(self):
        self.create_article()

        with mock.patch.object(
            type(admin_site), "has_audit_log_permission", return_value=True
        ):
            response = self.client_for(self.editor).get(AUDIT_LOG)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            [item for item in response.json()["entries"] if item["kind"] == "change"],
            [],
        )


class ChangeVersionTests(AuditLogTestCase):
    def test_the_version_of_a_deleted_object(self):
        article = self.create_article("Gone")
        self.client.patch(f"{ARTICLES}/{article.pk}", {"title": "Going"}, format="json")
        entry = LogEntry.objects.filter(action_flag=CHANGE).latest("pk")
        Article.objects.filter(pk=article.pk).delete()

        response = self.client.get(f"{AUDIT_LOG}/changes/{entry.pk}")

        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()
        self.assertFalse(data["object_exists"])
        self.assertEqual(data["fields"], ["title"])
        self.assertEqual(data["previous"]["title"], "Gone")
        self.assertEqual(data["data"]["title"], "Going")

    def test_no_version_is_not_found(self):
        article = Article.objects.create(title="Plain")
        entry = LogEntry.objects.create(
            user=self.superuser,
            action_flag=ADDITION,
            content_type=ContentType.objects.get_for_model(Article),
            object_id=article.pk,
            object_repr="Plain",
        )

        self.assertEqual(
            self.client.get(f"{AUDIT_LOG}/changes/{entry.pk}").status_code, 404
        )


class ExportTests(AuditLogTestCase):
    def test_csv_export_of_the_filtered_entries(self):
        self.login(password="wrong")
        self.create_article("Exported")

        response = self.client.get(f"{AUDIT_LOG}/export", {"export_format": "csv"})

        self.assertEqual(response.status_code, 200)
        self.assertIn("audit-log-", response["Content-Disposition"])
        text = b"".join(response.streaming_content).decode("utf-8-sig")
        rows = list(csv.reader(io.StringIO(text)))
        self.assertEqual(rows[0][:3], ["Time", "User", "Action"])
        self.assertEqual(rows[1][2], "Created")
        self.assertEqual(rows[1][4], "Exported")
        self.assertEqual(rows[2][2], "Failed sign-in")
        self.assertEqual(rows[2][9], "wrong_password")
        self.assertEqual(rows[2][10], "10.0.0.7")

        only_sign_ins = self.client.get(
            f"{AUDIT_LOG}/export", {"export_format": "csv", "action": "sign_in_failed"}
        )
        text = b"".join(only_sign_ins.streaming_content).decode("utf-8-sig")
        self.assertEqual(len(list(csv.reader(io.StringIO(text)))), 2)

    def test_excel_export(self):
        self.create_article("Exported")

        response = self.client.get(f"{AUDIT_LOG}/export", {"export_format": "xlsx"})

        self.assertEqual(response.status_code, 200)
        from openpyxl import load_workbook

        sheet = load_workbook(io.BytesIO(response.content)).active
        self.assertEqual(sheet.title, "Audit log")
        self.assertEqual(sheet.cell(2, 5).value, "Exported")
        self.assertIsInstance(sheet.cell(2, 1).value, datetime.datetime)

    def test_unknown_format_is_refused(self):
        response = self.client.get(f"{AUDIT_LOG}/export", {"export_format": "pdf"})

        self.assertEqual(response.status_code, 400)


class PruneTests(AuditLogTestCase):
    def test_prune_deletes_old_entries_and_events(self):
        article = self.create_article("Old")
        old = timezone.now() - datetime.timedelta(days=40)
        LogEntry.objects.update(action_time=old)
        SignInEvent.objects.create(kind=SignInEvent.SIGNED_IN, created_at=old)
        SignInEvent.objects.create(kind=SignInEvent.SIGNED_IN)

        with mock.patch.object(cs_settings, "AUDIT_LOG_KEEP_DAYS", 30):
            self.assertEqual(prune(), (1, 1))

        self.assertFalse(LogEntry.objects.filter(object_id=str(article.pk)).exists())
        self.assertEqual(SignInEvent.objects.count(), 1)

    def test_kept_forever_by_default(self):
        out = StringIO()

        call_command("content_studio_prune_audit_log", stdout=out)

        self.assertIn("every entry is kept", out.getvalue())

    def test_command_reports_what_it_deleted(self):
        out = StringIO()

        with mock.patch.object(cs_settings, "AUDIT_LOG_KEEP_DAYS", 30):
            call_command("content_studio_prune_audit_log", stdout=out)

        self.assertIn(
            "Deleted 0 activity log entries and 0 sign-in events", out.getvalue()
        )


def test_keep_days_check():
    with mock.patch.object(cs_settings, "AUDIT_LOG_KEEP_DAYS", 0):
        assert [check_id for check_id, _ in audit_log_errors()] == [
            "content_studio.E067"
        ]

    with mock.patch.object(cs_settings, "AUDIT_LOG_KEEP_DAYS", None):
        assert audit_log_errors() == []


def test_describe_user_agent():
    assert describe_user_agent(FIREFOX) == "Firefox on macOS"
    assert (
        describe_user_agent(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/131.0 Safari/537.36 Edg/131.0"
        )
        == "Edge on Windows"
    )
    assert (
        describe_user_agent(
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_1 like Mac OS X) "
            "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/18.1 Mobile/15E148 "
            "Safari/604.1"
        )
        == "Safari on iOS"
    )
    assert describe_user_agent("") == ""


def test_client_ip_follows_num_proxies():
    request = RequestFactory().get(
        "/", REMOTE_ADDR="10.0.0.1", HTTP_X_FORWARDED_FOR="203.0.113.9"
    )

    assert client_ip(request) == "10.0.0.1"

    with override_settings(REST_FRAMEWORK={"NUM_PROXIES": 1}):
        from rest_framework.settings import api_settings

        api_settings.reload()
        try:
            assert client_ip(request) == "203.0.113.9"
        finally:
            api_settings.reload()


def test_cursor_round_trip():
    key = timeline.Key(timezone.now(), 1, 42)

    assert timeline.Key.decode(key.encode()) == key
    assert timeline.Key.decode("nope") is None
