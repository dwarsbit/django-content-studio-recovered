"""
The developer tools: issues and requests gathered while DEBUG is on,
the endpoint that serves them and the header that announces changes.
"""

import logging
from unittest import mock

import pytest
from django.contrib.auth import models as auth_models
from django.core import checks
from django.http import HttpResponse
from django.test import RequestFactory
from rest_framework.test import APIClient

from content_studio import devtools
from content_studio.checks import devtools_errors
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article


@pytest.fixture(autouse=True)
def store():
    devtools.store.reset()
    yield devtools.store
    devtools.store.reset()


@pytest.fixture
def debug(settings):
    settings.DEBUG = True
    return settings


@pytest.fixture
def staff(db):
    return auth_models.User.objects.create_user(
        username="dev", password="x", is_staff=True, is_superuser=True
    )


def client_for(user):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


def test_on_only_while_debug_is_on(settings):
    settings.DEBUG = False
    assert not devtools.is_enabled()

    settings.DEBUG = True
    assert devtools.is_enabled()

    settings.CONTENT_STUDIO = {"DEVTOOLS": False}
    assert not devtools.is_enabled()


def test_report_does_nothing_without_debug(settings, store):
    settings.DEBUG = False

    devtools.report("warning", "Something to look at")

    assert store.get_issues() == []


def test_report_merges_repeats(debug, store):
    devtools.report("warning", "Slow", code="slow", key="a")
    devtools.report("warning", "Slower", code="slow", key="a")
    devtools.report("error", "Broken", code="err")

    broken, slow = store.get_issues()

    assert broken["message"] == "Broken"
    assert broken["level"] == "error"
    assert slow["count"] == 2
    assert slow["message"] == "Slower"
    assert slow["first_seen"] <= slow["last_seen"]


def test_report_keeps_a_bounded_number_of_issues(debug, store, monkeypatch):
    monkeypatch.setattr(devtools, "MAX_ISSUES", 3)

    for number in range(5):
        devtools.report("warning", f"Issue {number}")

    assert [issue["message"] for issue in store.get_issues()] == [
        "Issue 4",
        "Issue 3",
        "Issue 2",
    ]


def test_an_unknown_level_is_a_warning(debug, store):
    devtools.report("loud", "Hello")

    assert store.get_issues()[0]["level"] == "warning"


def test_content_studio_log_warnings_become_issues(debug, store):
    logger = logging.getLogger("content_studio.thumbnails")

    try:
        raise OSError("disk full")
    except OSError:
        logger.warning("Could not make a thumbnail of %s.", "a.jpg", exc_info=True)

    logger.warning("Could not make a thumbnail of %s.", "b.jpg")
    logger.info("Not an issue")

    [issue] = store.get_issues()
    assert issue["source"] == "log"
    assert issue["code"] == "content_studio.thumbnails"
    assert issue["message"] == "Could not make a thumbnail of b.jpg."
    assert issue["count"] == 2


def test_log_errors_with_details_and_opt_out(debug, store):
    logger = logging.getLogger("content_studio.webhooks")

    logger.error(
        "Delivery failed",
        extra={"devtools": {"title": "Webhook failed", "hint": "Check the URL"}},
    )
    logger.warning("Quiet", extra={"devtools": False})

    [issue] = store.get_issues()
    assert issue["level"] == "error"
    assert issue["title"] == "Webhook failed"
    assert issue["hint"] == "Check the URL"


def test_extra_loggers(debug, store, settings):
    settings.CONTENT_STUDIO = {"DEVTOOLS_LOGGERS": ["myproject"]}
    devtools.install_log_handler()

    try:
        logging.getLogger("myproject.shop").warning("Out of stock")
    finally:
        logging.getLogger("myproject").removeHandler(devtools.log_handler)

    assert store.get_issues()[0]["message"] == "Out of stock"


def test_system_checks_are_issues(debug, store):
    messages = [
        checks.Warning("Mind this", hint="Do that", id="content_studio.W001"),
        checks.Error("Broken", id="content_studio.E001", obj="ArticleStudio"),
        checks.Info("Fine", id="content_studio.I001"),
    ]

    with mock.patch.object(checks, "run_checks", return_value=messages):
        devtools.ensure_system_checks()
        devtools.ensure_system_checks()

    error, warning = store.get_issues()
    assert warning["code"] == "content_studio.W001"
    assert warning["hint"] == "Do that"
    assert warning["source"] == "check"
    assert error["level"] == "error"
    assert error["studio"] == "ArticleStudio"


def test_silenced_checks_stay_silent(debug, store, settings):
    settings.SILENCED_SYSTEM_CHECKS = ["content_studio.W001"]
    messages = [checks.Warning("Mind this", id="content_studio.W001")]

    with mock.patch.object(checks, "run_checks", return_value=messages):
        devtools.run_system_checks()

    assert store.get_issues() == []


def test_rerunning_checks_replaces_earlier_results(debug, store):
    with mock.patch.object(
        checks, "run_checks", return_value=[checks.Warning("Old", id="x.W1")]
    ):
        devtools.run_system_checks()

    devtools.report("warning", "Not a check")

    with mock.patch.object(
        checks, "run_checks", return_value=[checks.Warning("New", id="x.W2")]
    ):
        devtools.run_system_checks()

    assert [issue["message"] for issue in store.get_issues()] == [
        "New",
        "Not a check",
    ]


def test_record_counts_queries_and_reports_similar_ones(debug, store, staff):
    def view(request):
        for number in range(12):
            Article.objects.filter(pk=number).exists()
        return HttpResponse("ok")

    request = RequestFactory().get("/admin/api/content/testapp.article/42")
    request.user = staff

    response = devtools.record(view)(request)

    assert response[devtools.HEADER] == str(store.seq)

    [record] = store.get_requests(staff.pk)
    assert record["method"] == "GET"
    assert record["path"] == "content/testapp.article/42"
    assert record["status"] == 200
    assert record["queries"] == 12
    assert record["similar"][0]["count"] == 12
    assert len(record["slowest"]) == devtools.QUERIES_PER_REQUEST

    [issue] = store.get_issues()
    assert issue["code"] == "similar_queries"
    assert "× 12" in issue["snippet"]


def test_requests_are_per_user(debug, store, staff):
    request = RequestFactory().get("/api/me")
    request.user = staff

    devtools.record(lambda request: HttpResponse())(request)

    assert len(store.get_requests(staff.pk)) == 1
    assert store.get_requests(staff.pk + 1) == []


def test_record_turns_exceptions_into_issues(debug, store):
    def view(request):
        return 1 / 0

    request = RequestFactory().post("/api/content/testapp.article")

    with pytest.raises(ZeroDivisionError):
        devtools.record(view)(request)

    [issue] = store.get_issues()
    assert issue["level"] == "error"
    assert issue["message"] == "ZeroDivisionError: division by zero"
    assert issue["method"] == "POST"
    assert "1 / 0" in issue["stack"]
    assert store.requests[0]["status"] == 500


def test_record_does_nothing_without_debug(settings, store):
    settings.DEBUG = False
    request = RequestFactory().get("/api/me")

    response = devtools.record(lambda request: HttpResponse())(request)

    assert devtools.HEADER not in response
    assert not store.requests


def test_the_api_carries_the_header(debug, staff):
    response = client_for(staff).get("/api/me")

    assert response.status_code == 200
    assert devtools.HEADER in response


def test_the_api_has_no_header_without_debug(settings, staff):
    settings.DEBUG = False

    response = client_for(staff).get("/api/me")

    assert devtools.HEADER not in response


def test_the_endpoint_is_404_without_debug(settings, staff):
    settings.DEBUG = False
    client = client_for(staff)

    assert client.get("/api/devtools").status_code == 404
    assert client.delete("/api/devtools/issues").status_code == 404
    assert client.delete("/api/devtools/requests").status_code == 404
    assert client.post("/api/devtools/checks").status_code == 404


def test_the_endpoint_is_for_staff(debug, db):
    user = auth_models.User.objects.create_user(username="reader", password="x")

    assert APIClient().get("/api/devtools").status_code == 401
    assert client_for(user).get("/api/devtools").status_code in (401, 403)


def test_the_endpoint(debug, staff, store):
    client = client_for(staff)
    client.get("/api/me")
    devtools.report("warning", "Look here", code="mine")

    with mock.patch.object(checks, "run_checks", return_value=[]):
        data = client.get("/api/devtools").json()

    assert data["seq"] == store.seq
    assert [issue["message"] for issue in data["issues"]] == ["Look here"]
    # The developer tools' own requests are not recorded.
    assert [request["path"] for request in data["requests"]] == ["me"]
    labels = [item["label"] for item in data["info"]["environment"]]
    assert labels[:3] == ["Content Studio", "Django", "Python"]
    assert data["info"]["studios"]["testapp.article"]["studio"] == "ArticleAdmin"


def test_clearing(debug, staff, store):
    client = client_for(staff)
    client.get("/api/me")
    devtools.report("warning", "Look here")

    assert client.delete("/api/devtools/issues").status_code == 204
    assert client.delete("/api/devtools/requests").status_code == 204

    assert store.get_issues() == []
    assert store.get_requests(staff.pk) == []


def test_running_the_checks_again(debug, staff, store):
    with mock.patch.object(
        checks, "run_checks", return_value=[checks.Warning("Hm", id="x.W1")]
    ):
        response = client_for(staff).post("/api/devtools/checks")

    assert response.status_code == 204
    assert store.get_issues()[0]["code"] == "x.W1"


def test_discover_turns_the_button_on(debug, staff):
    data = client_for(staff).get("/api/discover").json()

    assert data["devtools"] is True
    assert data["debug"] is True


def test_discover_leaves_the_button_off_without_debug(settings, staff):
    settings.DEBUG = False
    data = client_for(staff).get("/api/discover").json()

    assert data["devtools"] is False
    assert data["debug"] is False


def test_the_public_page_does_not_say_debug_is_on(debug, client):
    # Everyone gets the page, signed in or not (security finding 10).
    html = client.get("/").content

    assert b"DCS_DEVTOOLS" not in html
    assert b"DCS_DEBUG" not in html


@pytest.mark.parametrize(
    "value, errors",
    [
        ({}, 0),
        ({"DEVTOOLS": False, "DEVTOOLS_LOGGERS": ["myproject"]}, 0),
        ({"DEVTOOLS": "yes"}, 1),
        ({"DEVTOOLS_LOGGERS": "myproject"}, 1),
        ({"DEVTOOLS": 1, "DEVTOOLS_LOGGERS": [""]}, 2),
    ],
)
def test_check_e049(settings, value, errors):
    settings.CONTENT_STUDIO = value

    found = devtools_errors()

    assert len(found) == errors
    assert all(check_id == "content_studio.E049" for check_id, _ in found)
