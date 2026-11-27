"""
Email activity: the logging backend, the log, the page's API, the status
row and the checks.
"""

import datetime
from contextlib import contextmanager
from unittest import mock

import pytest
from django.contrib.auth import models as auth_models
from django.core import mail
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.core.management import call_command
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.checks import email_activity_errors, email_activity_warnings
from content_studio.contrib.email_activity import KIND_HEADER, email_kind, kinds, log
from content_studio.contrib.email_activity.backends import (
    EmailBackend,
    get_delivery_backend_class,
)
from content_studio.contrib.email_activity.models import SentEmail
from content_studio.contrib.status import ServiceStatus
from content_studio.contrib.status import builtin
from content_studio.contrib.status import registry as status_registry
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import create_access_token

LOCMEM = "django.core.mail.backends.locmem.EmailBackend"


class FailingBackend(mail.backends.base.BaseEmailBackend):
    def send_messages(self, email_messages):
        raise ConnectionRefusedError("Connection refused")


class SilentBackend(mail.backends.base.BaseEmailBackend):
    def send_messages(self, email_messages):
        return 0


class UnreachableBackend(mail.backends.base.BaseEmailBackend):
    def open(self):
        raise TimeoutError("timed out")

    def send_messages(self, email_messages):
        return len(email_messages)


@contextmanager
def logging_backend(delivery=LOCMEM, **extra):
    """Send through the logging backend, delivering with delivery."""
    with (
        override_settings(EMAIL_BACKEND=log.LOGGING_BACKEND),
        mock.patch.object(cs_settings, "EMAIL_DELIVERY_BACKEND", delivery),
    ):
        for name, value in extra.items():
            mock.patch.object(cs_settings, name, value).start()
        try:
            yield
        finally:
            mock.patch.stopall()


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.fixture(autouse=True)
def no_prune_lock():
    cache.delete(log.PRUNE_CACHE_KEY)
    yield
    cache.delete(log.PRUNE_CACHE_KEY)


@pytest.fixture
def superuser(db):
    return auth_models.User.objects.create_user(
        username="root",
        email="root@example.com",
        password="x",
        is_staff=True,
        is_superuser=True,
    )


@pytest.fixture
def staff(db):
    return auth_models.User.objects.create_user(
        username="editor", password="x", is_staff=True
    )


# The logging backend


@pytest.mark.django_db
def test_a_sent_email_is_logged_without_its_body():
    with logging_backend():
        sent = mail.send_mail(
            "Hello",
            "The secret body",
            "Site <site@example.com>",
            ["sam@example.com"],
        )

    assert sent == 1
    assert len(mail.outbox) == 1

    email = SentEmail.objects.get()
    assert email.status == SentEmail.SENT
    assert email.subject == "Hello"
    assert email.from_email == "Site <site@example.com>"
    assert email.to == ["sam@example.com"]
    assert email.recipients == "sam@example.com"
    assert email.error == ""
    assert email.backend == "Local memory"
    assert email.finished_at is not None
    assert email.duration is not None
    assert email.size > 0

    stored = [str(getattr(email, field.attname)) for field in SentEmail._meta.fields]
    assert not any("secret body" in value for value in stored)


@pytest.mark.django_db
def test_the_logged_message_id_is_the_one_sent():
    with logging_backend():
        mail.send_mail("Hello", "Body", None, ["sam@example.com"])

    email = SentEmail.objects.get()
    assert email.message_id
    assert mail.outbox[0].message()["Message-ID"] == email.message_id


@pytest.mark.django_db
def test_cc_bcc_reply_to_and_attachments_are_logged():
    message = mail.EmailMessage(
        "Report",
        "Body",
        "site@example.com",
        ["a@example.com"],
        cc=["b@example.com"],
        bcc=["c@example.com"],
        reply_to=["d@example.com"],
    )
    message.attach("report.csv", "a,b\n1,2\n", "text/csv")

    with logging_backend():
        message.send()

    email = SentEmail.objects.get()
    assert email.cc == ["b@example.com"]
    assert email.bcc == ["c@example.com"]
    assert email.reply_to == ["d@example.com"]
    assert email.recipients == "a@example.com, b@example.com, c@example.com"
    assert email.attachments == [{"name": "report.csv", "type": "text/csv", "size": 8}]


@pytest.mark.django_db
def test_a_failed_email_is_logged_and_raises():
    with logging_backend(f"{__name__}.FailingBackend"):
        with pytest.raises(ConnectionRefusedError):
            mail.send_mail("Hello", "Body", None, ["sam@example.com"])

    email = SentEmail.objects.get()
    assert email.status == SentEmail.FAILED
    assert email.error == "ConnectionRefusedError: Connection refused"


@pytest.mark.django_db
def test_fail_silently_logs_the_failure_without_raising():
    with logging_backend(f"{__name__}.FailingBackend"):
        sent = mail.send_mail(
            "Hello", "Body", None, ["sam@example.com"], fail_silently=True
        )

    assert sent == 0
    assert SentEmail.objects.get().status == SentEmail.FAILED


@pytest.mark.django_db
def test_an_unreachable_backend_logs_every_email_as_failed():
    messages = [
        mail.EmailMessage("One", "Body", None, ["a@example.com"]),
        mail.EmailMessage("Two", "Body", None, ["b@example.com"]),
    ]

    with logging_backend(f"{__name__}.UnreachableBackend"):
        with pytest.raises(TimeoutError):
            mail.get_connection().send_messages(messages)

    assert list(SentEmail.objects.values_list("status", "error")) == [
        (SentEmail.FAILED, "TimeoutError: timed out"),
        (SentEmail.FAILED, "TimeoutError: timed out"),
    ]


@pytest.mark.django_db
def test_an_email_the_backend_did_not_send_is_failed():
    with logging_backend(f"{__name__}.SilentBackend"):
        assert mail.send_mail("Hello", "Body", None, ["sam@example.com"]) == 0

    email = SentEmail.objects.get()
    assert email.status == SentEmail.FAILED
    assert email.error == "The email backend did not send it."


@pytest.mark.django_db
def test_a_log_that_cannot_be_written_does_not_stop_the_email():
    with (
        logging_backend(),
        mock.patch.object(SentEmail.objects, "using", side_effect=RuntimeError),
    ):
        assert mail.send_mail("Hello", "Body", None, ["sam@example.com"]) == 1

    assert len(mail.outbox) == 1


@pytest.mark.django_db
def test_the_kind_comes_from_the_header_and_is_not_sent():
    message = mail.EmailMessage(
        "Hello", "Body", None, ["sam@example.com"], headers={KIND_HEADER: "order"}
    )

    with logging_backend():
        message.send()

    assert SentEmail.objects.get().kind == "order"
    assert KIND_HEADER not in mail.outbox[0].message()


@pytest.mark.django_db
def test_the_kind_and_sender_come_from_email_kind(superuser):
    with logging_backend(), email_kind(kinds.TEST, sent_by=superuser):
        mail.send_mail("Hello", "Body", None, ["sam@example.com"])

    email = SentEmail.objects.get()
    assert email.kind == kinds.TEST
    assert email.sent_by == superuser


def test_kind_labels():
    assert kinds.kind_label("") == "Other"
    assert kinds.kind_label(kinds.INVITE) == "Invite"
    assert kinds.kind_label("order_shipped") == "Order shipped"


@pytest.mark.django_db
def test_masking_hides_addresses_and_subjects():
    with logging_backend(EMAIL_ACTIVITY_MASK=True):
        mail.send_mail(
            "Your order", "Body", "site@example.com", ["Sam Lee <sam@example.com>"]
        )

    email = SentEmail.objects.get()
    assert email.to == ["s***@example.com"]
    assert email.subject == ""


@pytest.mark.django_db
def test_the_studio_emails_carry_their_kind(superuser):
    from content_studio.password_links import INVITE, send_link_mail

    with logging_backend():
        send_link_mail(superuser.pk, INVITE, "https://example.com/set", "Kim")
        send_link_mail(superuser.pk, None, "https://example.com/set", "Kim")

    assert list(SentEmail.objects.order_by("id").values_list("kind", flat=True)) == [
        kinds.INVITE,
        kinds.PASSWORD_LINK,
    ]


def test_the_delivery_backend_cannot_be_the_logging_backend():
    with mock.patch.object(cs_settings, "EMAIL_DELIVERY_BACKEND", log.LOGGING_BACKEND):
        with pytest.raises(ImproperlyConfigured):
            get_delivery_backend_class()


def test_the_delivery_backend_must_import():
    with mock.patch.object(cs_settings, "EMAIL_DELIVERY_BACKEND", "nope.Backend"):
        with pytest.raises(ImproperlyConfigured):
            EmailBackend()


# Pruning


@pytest.mark.django_db
def test_prune_deletes_emails_older_than_keep_days():
    now = timezone.now()
    old = SentEmail.objects.create(
        status="sent", created_at=now - datetime.timedelta(days=31)
    )
    new = SentEmail.objects.create(
        status="sent", created_at=now - datetime.timedelta(days=29)
    )

    assert log.prune() == 1
    assert list(SentEmail.objects.all()) == [new]
    assert not SentEmail.objects.filter(pk=old.pk).exists()


@pytest.mark.django_db
def test_keep_days_none_keeps_everything():
    SentEmail.objects.create(
        status="sent", created_at=timezone.now() - datetime.timedelta(days=400)
    )

    with mock.patch.object(cs_settings, "EMAIL_ACTIVITY_KEEP_DAYS", None):
        assert log.prune() == 0

    assert SentEmail.objects.count() == 1


@pytest.mark.django_db
def test_sending_prunes_at_most_once_an_hour():
    with mock.patch.object(log, "prune") as prune, logging_backend():
        mail.send_mail("One", "Body", None, ["a@example.com"])
        mail.send_mail("Two", "Body", None, ["a@example.com"])

    assert prune.call_count == 1


@pytest.mark.django_db
def test_the_prune_command(capsys):
    SentEmail.objects.create(
        status="sent", created_at=timezone.now() - datetime.timedelta(days=31)
    )

    call_command("content_studio_prune_emails")

    assert "Deleted 1 emails older than 30 days." in capsys.readouterr().out
    assert not SentEmail.objects.exists()


# Checks


def test_checks_pass_by_default():
    assert email_activity_errors() == []
    assert email_activity_warnings() == []


def test_e062_for_a_bad_delivery_backend_or_keep_days():
    with mock.patch.object(cs_settings, "EMAIL_DELIVERY_BACKEND", "nope.Backend"):
        assert [check for check, _ in email_activity_errors()] == [
            "content_studio.E062"
        ]

    with mock.patch.object(cs_settings, "EMAIL_ACTIVITY_KEEP_DAYS", 0):
        assert [check for check, _ in email_activity_errors()] == [
            "content_studio.E062"
        ]


def test_w035_when_emails_are_not_logged():
    with override_settings(
        EMAIL_BACKEND="django.core.mail.backends.console.EmailBackend"
    ):
        assert [check for check, _ in email_activity_warnings()] == [
            "content_studio.W035"
        ]

    with logging_backend():
        assert email_activity_warnings() == []


# The API


@pytest.mark.django_db
def test_only_superusers_see_the_log(staff):
    client = client_for(staff)

    assert client.get("/api/email-activity").status_code == 403
    assert client.post("/api/email-activity/test", {}).status_code == 403


def test_anonymous_users_are_refused():
    assert APIClient().get("/api/email-activity").status_code in (401, 403)


@pytest.mark.django_db
def test_the_list(superuser):
    now = timezone.now()
    SentEmail.objects.create(
        status="sent",
        subject="Welcome",
        kind=kinds.INVITE,
        to=["sam@example.com"],
        recipients="sam@example.com",
        created_at=now - datetime.timedelta(minutes=2),
    )
    SentEmail.objects.create(
        status="failed",
        subject="Order shipped",
        kind="order",
        error="SMTPRecipientsRefused",
        to=["kim@example.com"],
        recipients="kim@example.com",
        created_at=now - datetime.timedelta(minutes=1),
    )

    data = client_for(superuser).get("/api/email-activity").json()

    assert [email["subject"] for email in data["emails"]] == [
        "Order shipped",
        "Welcome",
    ]
    assert data["emails"][0]["error"] == "SMTPRecipientsRefused"
    assert data["emails"][0]["kind_label"] == "Order"
    assert data["total"] == 2
    assert data["counts"] == {"all": 2, "sent": 1, "failed": 1}
    assert data["kinds"] == [
        {"value": "invite", "label": "Invite"},
        {"value": "order", "label": "Order"},
    ]
    assert data["summary"]["sent"] == 1
    assert data["summary"]["failed"] == 1
    assert data["summary"]["keep_days"] == 30
    assert data["summary"]["logging"] is False
    assert data["summary"]["masked"] is False
    assert data["your_email"] == "root@example.com"


@pytest.mark.django_db
def test_the_list_filters(superuser):
    now = timezone.now()

    for index, (status, kind, to) in enumerate(
        [
            ("sent", "invite", "sam@example.com"),
            ("failed", "invite", "kim@example.com"),
            ("sent", "", "lee@example.org"),
        ]
    ):
        SentEmail.objects.create(
            status=status,
            kind=kind,
            subject=f"Email {index}",
            recipients=to,
            created_at=now - datetime.timedelta(minutes=index),
        )

    client = client_for(superuser)

    def subjects(**params):
        data = client.get("/api/email-activity", params).json()
        return [email["subject"] for email in data["emails"]], data

    assert subjects(status="failed")[0] == ["Email 1"]
    assert subjects(kind="invite")[0] == ["Email 0", "Email 1"]
    assert subjects(kind="")[0] == ["Email 2"]
    assert subjects(q="example.org")[0] == ["Email 2"]

    found, data = subjects(kind="invite", status="sent")
    assert found == ["Email 0"]
    assert data["total"] == 1
    assert data["counts"] == {"all": 2, "sent": 1, "failed": 1}


@pytest.mark.django_db
def test_the_list_pages(superuser):
    now = timezone.now()
    SentEmail.objects.bulk_create(
        SentEmail(
            status="sent",
            subject=f"Email {index}",
            created_at=now - datetime.timedelta(seconds=index),
        )
        for index in range(55)
    )
    client = client_for(superuser)

    first = client.get("/api/email-activity").json()
    second = client.get("/api/email-activity", {"offset": 50}).json()

    assert len(first["emails"]) == 50
    assert [email["subject"] for email in second["emails"]] == [
        f"Email {index}" for index in range(50, 55)
    ]
    assert second["total"] == 55


@pytest.mark.django_db
def test_send_a_test_email(superuser):
    with logging_backend():
        response = client_for(superuser).post(
            "/api/email-activity/test", {"to": "kim@example.com"}, format="json"
        )

    assert response.status_code == 200
    assert response.json() == {"detail": "Test email sent to kim@example.com."}
    assert mail.outbox[0].to == ["kim@example.com"]
    assert "root" in mail.outbox[0].body

    email = SentEmail.objects.get()
    assert email.kind == kinds.TEST
    assert email.sent_by == superuser


@pytest.mark.django_db
def test_a_test_email_needs_a_valid_address(superuser):
    response = client_for(superuser).post(
        "/api/email-activity/test", {"to": "not an address"}, format="json"
    )

    assert response.status_code == 400
    assert response.json() == {"to": ["Enter a valid email address."]}
    assert mail.outbox == []


@pytest.mark.django_db
def test_a_failed_test_email_returns_the_error(superuser):
    with logging_backend(f"{__name__}.FailingBackend"):
        response = client_for(superuser).post(
            "/api/email-activity/test", {"to": "kim@example.com"}, format="json"
        )

    assert response.status_code == 400
    assert response.json() == {"detail": "ConnectionRefusedError: Connection refused"}
    assert SentEmail.objects.get().status == SentEmail.FAILED


# Discover and the status page


@pytest.mark.django_db
def test_discover_tells_superusers_only(superuser, staff):
    assert client_for(superuser).get("/api/discover").json()["email_activity"] == {
        "enabled": True
    }
    assert client_for(staff).get("/api/discover").json()["email_activity"] == {
        "enabled": False
    }


def test_the_email_status_row_links_to_the_page():
    service = next(
        s for s in status_registry.get_services() if s.key == "content_studio.email"
    )

    assert service.url == "email-activity"


@pytest.mark.django_db
def test_the_email_status_row_counts_and_degrades_on_failures():
    SentEmail.objects.create(status="sent", created_at=timezone.now())

    result = builtin.check_email()
    assert result.status == ServiceStatus.UNKNOWN
    assert "1 sent in 24 hours" in result.detail

    SentEmail.objects.create(status="failed", created_at=timezone.now())

    result = builtin.check_email()
    assert result.status == ServiceStatus.DEGRADED
    assert result.message == "1 of 2 emails failed in the last 24 hours."


@pytest.mark.django_db
@pytest.mark.skipif(not hasattr(mail, "mailers"), reason="Django 6.1 and later")
def test_the_logging_backend_as_a_mailer():
    with (
        override_settings(MAILERS={"default": {"BACKEND": log.LOGGING_BACKEND}}),
        mock.patch.object(cs_settings, "EMAIL_DELIVERY_BACKEND", LOCMEM),
    ):
        assert log.is_logging()
        mail.send_mail("Hello", "Body", None, ["sam@example.com"])

    assert SentEmail.objects.get().status == SentEmail.SENT
    assert len(mail.outbox) == 1
