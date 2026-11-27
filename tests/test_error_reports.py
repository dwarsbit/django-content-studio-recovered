"""
Error reports: the settings, the email handler, the notification, Sentry,
the status page row and card, and the checks.
"""

import logging
import sys
import types
from contextlib import contextmanager
from unittest import mock

import pytest
from django.contrib.auth import get_user_model
from django.core import mail
from django.core.cache import cache
from django.test import override_settings
from rest_framework.test import APIClient

from content_studio import error_reports, logs
from content_studio.checks import check_error_reports
from content_studio.contrib.status import ServiceStatus
from content_studio.error_reports import config, handler, notifying, sentry, status
from content_studio.error_reports.handler import ErrorReportHandler
from content_studio.notifications import events as notification_events
from content_studio.notifications.models import Notification
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import create_access_token

User = get_user_model()


@contextmanager
def setting(**values):
    with mock.patch.multiple(cs_settings, **values):
        yield


@contextmanager
def email_mode(**values):
    """Email mode with the event registered, as ready() does."""
    with setting(ERROR_REPORTS="email", **values):
        notifying.register_error_event()

        try:
            yield
        finally:
            notification_events._registry.pop(notifying.EVENT_KEY, None)


def make_record(msg="Order %s failed", args=("42",), exc=None, name="shop.orders"):
    exc_info = None

    if exc is not None:
        try:
            raise exc
        except Exception:
            exc_info = sys.exc_info()

    return logging.LogRecord(
        name, logging.ERROR, __file__, 10, msg, args, exc_info, func="test"
    )


@pytest.fixture(autouse=True)
def on_commit_now():
    """Notifications are written on commit: right away here."""
    with mock.patch(
        "django.db.transaction.on_commit", lambda func, *args, **kwargs: func()
    ):
        yield


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser(
        "boss", "boss@example.com", "pw", is_staff=True
    )


def emit(record):
    ErrorReportHandler().handle(record)


# Settings ------------------------------------------------------------


def test_off_by_default():
    assert config.get_mode() == "off"
    assert not config.is_active()


@pytest.mark.parametrize(
    "value,mode",
    [("EMAIL", "email"), (" sentry ", "sentry"), ("", "off"), (None, "off")],
)
def test_mode_is_read_loosely(value, mode):
    with setting(ERROR_REPORTS=value):
        assert config.get_mode() == mode


@pytest.mark.parametrize(
    "value,expected",
    [
        ("a@example.com, b@example.com", ["a@example.com", "b@example.com"]),
        (["a@example.com"], ["a@example.com"]),
        ("", []),
        (None, []),
    ],
)
def test_error_email_accepts_a_list_or_a_string(value, expected):
    with setting(ERROR_EMAIL=value):
        assert config.get_error_email() == expected


@pytest.mark.parametrize("value,rate", [("0.25", 0.25), (1, 1.0), ("", 0.0)])
def test_sample_rate(value, rate):
    with setting(SENTRY_TRACES_SAMPLE_RATE=value):
        assert config.get_sample_rate() == rate


@pytest.mark.parametrize("value", ["2", "-0.1", "lots", True])
def test_bad_sample_rate_is_an_error(value):
    with setting(SENTRY_TRACES_SAMPLE_RATE=value):
        ids = [message.id for message in check_error_reports()]

    assert ids == ["content_studio.E064"]


def test_checks():
    with setting(ERROR_REPORTS="loud"):
        assert [m.id for m in check_error_reports()] == ["content_studio.E064"]

    with setting(ERROR_REPORTS="email", ERROR_EMAIL="not an address"):
        assert [m.id for m in check_error_reports()] == ["content_studio.E064"]

    with setting(ERROR_REPORTS="sentry", SENTRY_DSN=""):
        assert [m.id for m in check_error_reports()] == ["content_studio.W039"]

    with setting(ERROR_REPORTS="sentry", SENTRY_DSN="https://k@sentry.io/1"):
        assert check_error_reports() == []


def test_sentry_mode_without_the_sdk_is_an_error():
    with (
        setting(ERROR_REPORTS="sentry", SENTRY_DSN="https://k@sentry.io/1"),
        mock.patch.dict(sys.modules, {"sentry_sdk": None}),
    ):
        assert [m.id for m in check_error_reports()] == ["content_studio.E064"]


def test_warns_when_admins_are_mailed_too():
    from django.utils.log import AdminEmailHandler

    admin_handler = AdminEmailHandler()
    django_logger = logging.getLogger("django")
    django_logger.addHandler(admin_handler)

    try:
        with (
            email_mode(),
            override_settings(ADMINS=[("Ops", "ops@example.com")]),
        ):
            ids = [m.id for m in check_error_reports()]
    finally:
        django_logger.removeHandler(admin_handler)

    assert ids == ["content_studio.W038"]


# Signatures -------------------------------------------------------------


def test_signature_groups_by_logger_type_and_line():
    first = make_record(exc=ValueError("one"))
    second = make_record(exc=ValueError("two"))
    other_type = make_record(exc=KeyError("one"))
    other_logger = make_record(exc=ValueError("one"), name="shop.payments")

    assert handler.signature(first) == handler.signature(second)
    assert handler.signature(first) != handler.signature(other_type)
    assert handler.signature(first) != handler.signature(other_logger)


def test_signature_without_exception_uses_the_unformatted_message():
    assert handler.signature(make_record(args=("1",))) == handler.signature(
        make_record(args=("2",))
    )
    assert handler.signature(make_record(msg="Other")) != handler.signature(
        make_record()
    )


def test_summary_is_the_first_line_at_most_150_characters():
    assert handler.summary(make_record(msg="Line one\nLine two", args=())) == (
        "Line one"
    )
    assert len(handler.summary(make_record(msg="x" * 300, args=()))) == 150
    assert (
        handler.summary(make_record(msg="", args=(), exc=ValueError("boom")))
        == "ValueError: boom"
    )


# Email mode -------------------------------------------------------------


@pytest.mark.django_db
def test_reports_by_email_and_notification(superuser):
    with email_mode():
        emit(make_record(exc=ValueError("boom")))

    assert len(mail.outbox) == 1
    message = mail.outbox[0]
    assert message.to == ["boss@example.com"]
    assert message.subject == "[Content Studio] ERROR: Order 42 failed"
    assert "ValueError: boom" in message.body
    assert "Logger: shop.orders" in message.body

    notification = Notification.objects.get(recipient=superuser)
    assert notification.event == notifying.EVENT_KEY
    assert notification.level == "error"
    assert notification.get_title() == "Order 42 failed"
    assert notification.get_body() == "shop.orders"


@pytest.mark.django_db
def test_error_email_replaces_the_superusers(superuser):
    with email_mode(ERROR_EMAIL="ops@example.com,dev@example.com"):
        emit(make_record())

    assert mail.outbox[0].to == ["ops@example.com", "dev@example.com"]


@pytest.mark.django_db
def test_the_same_error_is_reported_once_an_hour(superuser):
    with email_mode():
        emit(make_record(exc=ValueError("one")))
        emit(make_record(exc=ValueError("two")))

        assert len(mail.outbox) == 1

        # The hour passed: reported again, and the notification counts up.
        cache.clear()
        emit(make_record(exc=ValueError("three")))

    assert len(mail.outbox) == 2
    notification = Notification.objects.get(recipient=superuser)
    assert notification.count == 2


@pytest.mark.django_db
def test_request_id_is_in_the_email(superuser):
    record = make_record()
    record.request_id = "abc123"

    with email_mode():
        emit(record)

    assert "Request ID: abc123" in mail.outbox[0].body


@pytest.mark.django_db
def test_without_notifications_app_only_email(superuser):
    with (
        email_mode(),
        mock.patch.object(notifying, "notifications_installed", return_value=False),
    ):
        emit(make_record())

    assert len(mail.outbox) == 1
    assert not Notification.objects.exists()


@pytest.mark.django_db
def test_a_failed_report_never_raises(superuser, caplog):
    with (
        email_mode(),
        mock.patch("django.core.mail.send_mail", side_effect=OSError("smtp down")),
        caplog.at_level(logging.WARNING, logger="content_studio.error_reports"),
    ):
        emit(make_record())

    assert "Could not report an error" in caplog.text


@pytest.mark.django_db
def test_ignores_its_own_logger_and_disallowed_host(superuser):
    with email_mode():
        emit(make_record(name="content_studio.error_reports"))
        emit(make_record(name="django.security.DisallowedHost"))

    assert mail.outbox == []


@pytest.mark.django_db
def test_no_recursion(superuser):
    """An error logged while reporting is not reported."""
    root_handler = ErrorReportHandler()

    def send_mail(*args, **kwargs):
        root_handler.handle(make_record(msg="Nested", args=()))
        mail.outbox.append("sent")

    with email_mode(), mock.patch("django.core.mail.send_mail", send_mail):
        root_handler.handle(make_record())

    assert mail.outbox == ["sent"]


def test_install_handler_on_root_and_non_propagating_loggers():
    quiet = logging.getLogger("tests.quiet")
    quiet.propagate = False
    quiet.addHandler(logging.NullHandler())
    disallowed = logging.getLogger("django.security.DisallowedHost")
    disallowed_propagate = disallowed.propagate
    disallowed.propagate = False
    disallowed.addHandler(logging.NullHandler())

    try:
        added = handler.install_handler()

        assert "root" in added
        assert "tests.quiet" in added
        assert "django.security.DisallowedHost" not in added
        # Twice adds nothing.
        assert handler.install_handler() == []
    finally:
        handler.uninstall_handler()
        quiet.handlers.clear()
        quiet.propagate = True
        disallowed.handlers.clear()
        disallowed.propagate = disallowed_propagate


def test_install_handler_keeps_a_project_setup():
    project = logging.getLogger("tests.project")
    project.addHandler(ErrorReportHandler())

    try:
        assert handler.install_handler() == []
        assert not any(isinstance(h, ErrorReportHandler) for h in logging.root.handlers)
    finally:
        handler.uninstall_handler()


def test_set_up_does_nothing_while_debug_is_on():
    with (
        email_mode(),
        override_settings(DEBUG=True),
        mock.patch.object(handler, "install_handler") as install,
    ):
        error_reports.set_up()

    install.assert_not_called()


def test_set_up_installs_the_handler_in_email_mode():
    with (
        setting(ERROR_REPORTS="email"),
        override_settings(DEBUG=False),
        mock.patch.object(handler, "install_handler") as install,
    ):
        error_reports.set_up()

    notification_events._registry.pop(notifying.EVENT_KEY, None)
    install.assert_called_once()


def test_set_up_skips_bad_settings():
    with (
        setting(ERROR_REPORTS="email", ERROR_EMAIL="nope"),
        override_settings(DEBUG=False),
        mock.patch.object(handler, "install_handler") as install,
    ):
        error_reports.set_up()

    notification_events._registry.pop(notifying.EVENT_KEY, None)
    install.assert_not_called()


# Sentry mode ------------------------------------------------------------


class FakeClient:
    def __init__(self, active):
        self.active = active

    def is_active(self):
        return self.active


@contextmanager
def fake_sentry(active=False):
    sdk = types.ModuleType("sentry_sdk")
    sdk.init = mock.Mock()
    sdk.get_client = lambda: FakeClient(active)
    integrations = types.ModuleType("sentry_sdk.integrations")
    logging_integration = types.ModuleType("sentry_sdk.integrations.logging")
    logging_integration.ignore_logger = mock.Mock()

    with mock.patch.dict(
        sys.modules,
        {
            "sentry_sdk": sdk,
            "sentry_sdk.integrations": integrations,
            "sentry_sdk.integrations.logging": logging_integration,
        },
    ):
        yield sdk, logging_integration


def test_init_sentry():
    with (
        setting(
            ERROR_REPORTS="sentry",
            SENTRY_DSN="https://key@sentry.io/1",
            SENTRY_RELEASE="abc",
            SENTRY_TRACES_SAMPLE_RATE="0.1",
        ),
        fake_sentry() as (sdk, logging_integration),
    ):
        assert sentry.init_sentry()

    options = sdk.init.call_args.kwargs
    assert options["dsn"] == "https://key@sentry.io/1"
    assert options["environment"] == "production"
    assert options["release"] == "abc"
    assert options["traces_sample_rate"] == 0.1
    assert options["send_default_pii"] is False
    assert options["max_request_body_size"] == "never"
    logging_integration.ignore_logger.assert_called_once_with(
        "django.security.DisallowedHost"
    )


def test_init_sentry_without_dsn_warns(caplog):
    with (
        setting(ERROR_REPORTS="sentry", SENTRY_DSN=""),
        fake_sentry() as (sdk, _),
        caplog.at_level(logging.WARNING, logger="content_studio.error_reports"),
    ):
        assert not sentry.init_sentry()

    sdk.init.assert_not_called()
    assert "SENTRY_DSN is empty" in caplog.text


def test_init_sentry_leaves_a_project_setup_alone():
    with (
        setting(ERROR_REPORTS="sentry", SENTRY_DSN="https://key@sentry.io/1"),
        fake_sentry(active=True) as (sdk, _),
    ):
        assert not sentry.init_sentry()

    sdk.init.assert_not_called()


def test_before_send_tags_the_request_id_and_drops_private_data():
    event = {
        "request": {
            "cookies": {"sessionid": "x"},
            "data": "secret",
            "headers": {"Cookie": "x", "Authorization": "Bearer y", "Accept": "*/*"},
        }
    }
    token = logs._request_id.set("req-1")

    try:
        event = sentry.before_send(event, {})
    finally:
        logs._request_id.reset(token)

    assert event["tags"] == {"request_id": "req-1"}
    assert event["request"] == {"headers": {"Accept": "*/*"}}


# Status page ------------------------------------------------------------


@pytest.mark.django_db
def test_status_row(superuser):
    with setting(ERROR_REPORTS="email"), override_settings(DEBUG=False):
        result = status.check_error_reports()

    assert result.status == ServiceStatus.OK
    assert str(result.detail) == "Email to 1 recipient"


@pytest.mark.django_db
def test_status_row_without_recipients():
    with setting(ERROR_REPORTS="email"), override_settings(DEBUG=False):
        result = status.check_error_reports()

    assert result.status == ServiceStatus.DEGRADED


def test_status_row_sentry():
    with (
        setting(ERROR_REPORTS="sentry", SENTRY_DSN="", SENTRY_ENVIRONMENT="staging"),
        fake_sentry(),
        override_settings(DEBUG=False),
    ):
        assert status.check_error_reports().status == ServiceStatus.DOWN

        with setting(SENTRY_DSN="https://key@sentry.io/1"):
            result = status.check_error_reports()

    assert result.status == ServiceStatus.OK
    assert str(result.detail) == "Sentry · staging"


@pytest.mark.django_db
def test_status_row_is_unknown_while_debug_is_on(superuser):
    with setting(ERROR_REPORTS="email"), override_settings(DEBUG=True):
        assert status.check_error_reports().status == ServiceStatus.UNKNOWN


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.mark.django_db
def test_recent_errors_endpoint(superuser):
    with email_mode():
        emit(make_record(exc=ValueError("boom")))
        cache.clear()
        emit(make_record(exc=ValueError("again")))
        response = client_for(superuser).get("/api/status/errors")

    assert response.status_code == 200
    data = response.json()
    assert data["enabled"] is True
    [error] = data["errors"]
    assert error["title"] == "Order 42 failed"
    assert error["logger"] == "shop.orders"
    assert error["count"] == 2
    assert error["read"] is False


@pytest.mark.django_db
def test_recent_errors_disabled_outside_email_mode(superuser):
    response = client_for(superuser).get("/api/status/errors")

    assert response.json() == {"enabled": False, "errors": []}


@pytest.mark.django_db
def test_recent_errors_needs_the_status_permission(db):
    editor = User.objects.create_user("editor", "e@example.com", "pw", is_staff=True)

    with email_mode():
        response = client_for(editor).get("/api/status/errors")

    assert response.status_code == 403
