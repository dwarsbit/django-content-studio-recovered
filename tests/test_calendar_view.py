"""
Tests for the calendar list view (content_studio.list_views): the
config and its serialization, the calendar endpoint (ranges, the tray,
search and filters, the cap), saving a dragged date through the table
edit save, and the checks (E002, E059, E060).
"""

from datetime import datetime, timedelta, timezone as tz
from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, ModelStudio, admin_site
from content_studio.checks import list_config_errors
from content_studio.list_views import CalendarView, get_drag_fields
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.admin import ArticleAdmin, StoryAdmin
from tests.testapp.models import Article, Story

ARTICLES = "/api/content/testapp.article"
STORIES = "/api/content/testapp.story"


def api_for(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return api


@pytest.fixture
def user(db):
    return User.objects.create_superuser(username="admin", password="x")


@pytest.fixture
def client(user):
    return api_for(user)


@pytest.fixture
def request_(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


@pytest.fixture
def article_calendar():
    """Articles on a calendar of published_at (no publishing)."""
    with mock.patch.object(
        ArticleAdmin, "list_views", ["table", CalendarView("published_at")]
    ):
        yield


@pytest.fixture
def story_calendar():
    """Stories on the calendar of their publishing date."""
    with mock.patch.object(StoryAdmin, "list_views", ["table", "calendar"]):
        yield


def staff(*codenames):
    user = User.objects.create_user(username="staff", password="x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


def at(day, hour=9):
    return datetime(2026, 11, day, hour, tzinfo=tz.utc)


def month(client, url=ARTICLES, **params):
    return client.get(
        f"{url}/calendar",
        {"from": "2026-11-01T00:00:00Z", "to": "2026-12-01T00:00:00Z", **params},
    )


# Config and metadata


def test_bare_calendar_is_the_publishing_date(story_calendar, request_):
    views = AdminSerializer(StoryAdmin(Story, admin_site)).serialize(request_)["list"][
        "views"
    ]

    assert views[0] == "table"
    assert views[1] == {
        "type": "calendar",
        "key": "calendar:published_at",
        "field": "published_at",
        "end": None,
        "label": "Published at",
        "date_only": False,
        "nullable": True,
        "publishing": True,
        "editable": True,
    }


def test_calendar_of_another_field(article_calendar, request_):
    views = AdminSerializer(ArticleAdmin(Article, admin_site)).serialize(request_)[
        "list"
    ]["views"]

    assert views[1]["key"] == "calendar:published_at"
    assert views[1]["publishing"] is False
    assert views[1]["editable"] is True


def test_label_and_editable_can_be_set(request_):
    with mock.patch.object(
        ArticleAdmin,
        "list_views",
        [CalendarView("published_at", label="Go-live", editable=False)],
    ):
        view = AdminSerializer(ArticleAdmin(Article, admin_site)).serialize(request_)[
            "list"
        ]["views"][0]

    assert view["label"] == "Go-live"
    assert view["editable"] is False


def test_not_editable_without_change_permission(article_calendar, db):
    request = RequestFactory().get("/")
    request.user = staff("view_article")
    studio = ArticleAdmin(Article, admin_site)

    assert get_drag_fields(studio, request) == []
    view = AdminSerializer(studio).serialize(request)["list"]["views"][1]
    assert view["editable"] is False


def test_publishing_calendar_needs_publish_permission(story_calendar, db):
    request = RequestFactory().get("/")
    request.user = staff("view_story", "change_story")
    view = AdminSerializer(StoryAdmin(Story, admin_site)).serialize(request)["list"][
        "views"
    ][1]

    assert view["editable"] is False


def test_publishing_calendar_is_read_only_with_required_review(
    story_calendar, request_
):
    from content_studio.review import Review

    with mock.patch.object(StoryAdmin, "review", Review(required=True), create=True):
        view = AdminSerializer(StoryAdmin(Story, admin_site)).serialize(request_)[
            "list"
        ]["views"][1]

    assert view["editable"] is False


def test_publishing_dates_are_never_drag_fields(story_calendar, request_):
    assert get_drag_fields(StoryAdmin(Story, admin_site), request_) == []


# The calendar endpoint


def test_lists_the_range(article_calendar, client):
    Article.objects.create(title="Before", published_at=at(1) - timedelta(days=1))
    Article.objects.create(title="In", published_at=at(12))
    Article.objects.create(title="Last", published_at=at(30, 23))
    Article.objects.create(title="After", published_at=at(30) + timedelta(days=2))
    Article.objects.create(title="No date")

    data = month(client).json()

    assert sorted(row["title"] for row in data["results"]) == ["In", "Last"]
    assert data["truncated"] is False


def test_rows_carry_the_date_and_item_display(article_calendar, client):
    Article.objects.create(title="In", published_at=at(12))

    row = month(client).json()["results"][0]

    assert row["published_at"].startswith("2026-11-12")
    assert row["list_item_display"]["title"] == "In"


def test_the_date_field_is_in_rows_outside_table_display(client):
    Story.objects.create(title="Soon", published_at=at(20))

    with mock.patch.object(StoryAdmin, "list_views", ["table", "calendar"]):
        row = month(client, STORIES).json()["results"][0]

    assert row["published_at"].startswith("2026-11-20")
    assert row["__publishing__"]["published_at"].startswith("2026-11-20")


def test_search_and_filters_apply(article_calendar, client):
    Article.objects.create(title="Apple", published_at=at(3), status="draft")
    Article.objects.create(title="Banana", published_at=at(4), status="published")
    Article.objects.create(title="Avocado", published_at=at(5), status="published")

    searched = month(client, search="a").json()["results"]
    filtered = month(client, status="published").json()["results"]

    assert {row["title"] for row in searched} == {"Apple", "Banana", "Avocado"}
    assert {row["title"] for row in filtered} == {"Banana", "Avocado"}


def test_unscheduled_lists_items_without_a_date(article_calendar, client):
    Article.objects.create(title="Dated", published_at=at(3))
    Article.objects.create(title="Undated")

    data = client.get(f"{ARTICLES}/calendar", {"unscheduled": "1"}).json()

    assert [row["title"] for row in data["results"]] == ["Undated"]
    assert data["count"] == 1


def test_a_busy_range_is_cut(article_calendar, client):
    Article.objects.bulk_create(
        Article(title=f"A{i}", published_at=at(10)) for i in range(4)
    )

    with mock.patch("content_studio.list_views.CALENDAR_MAX_ITEMS", 3):
        data = month(client).json()

    assert len(data["results"]) == 3
    assert data["truncated"] is True


def test_bounds_must_be_dates(article_calendar, client):
    response = client.get(f"{ARTICLES}/calendar", {"from": "soon", "to": "later"})

    assert response.status_code == 400


def test_unknown_calendar(article_calendar, client):
    response = client.get(f"{ARTICLES}/calendar", {"view": "calendar:title"})

    assert response.status_code == 404


def test_no_calendar(client, db):
    assert month(client).status_code == 404


def test_needs_view_permission(article_calendar, db):
    client = api_for(staff())

    assert month(client).status_code == 403


def test_end_field_shows_spans_that_overlap(client, db):
    """With an end, an object shows on every day of its span: one that
    started before the range and ends in it is listed."""
    start = at(1) - timedelta(days=3)
    Story.objects.create(title="Spans", published_at=start, unpublish_at=at(2))
    Story.objects.create(
        title="Ended", published_at=start, unpublish_at=at(1) - timedelta(days=1)
    )
    Story.objects.create(title="Open", published_at=start)
    Story.objects.create(title="Inside", published_at=at(5))

    with mock.patch.object(
        StoryAdmin, "list_views", [CalendarView("published_at", end="unpublish_at")]
    ):
        data = month(client, STORIES).json()

    assert sorted(row["title"] for row in data["results"]) == ["Inside", "Spans"]


# Saving a dragged date


def test_drag_saves_the_date_through_table_edit(article_calendar, client):
    article = Article.objects.create(title="Move me", published_at=at(3))

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {
            "values": {"published_at": at(10).isoformat()},
            "base": {
                "published_at": client.get(f"{ARTICLES}/{article.pk}").json()[
                    "published_at"
                ]
            },
        },
        format="json",
    )

    assert response.status_code == 200, response.json()
    article.refresh_from_db()
    assert article.published_at == at(10)


def test_drag_is_refused_without_a_calendar(client, db):
    article = Article.objects.create(title="Stay", published_at=at(3))

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {"values": {"published_at": at(10).isoformat()}},
        format="json",
    )

    assert response.status_code == 400


def test_drag_is_refused_when_not_editable(client, db):
    article = Article.objects.create(title="Stay", published_at=at(3))

    with mock.patch.object(
        ArticleAdmin, "list_views", [CalendarView("published_at", editable=False)]
    ):
        response = client.post(
            f"{ARTICLES}/{article.pk}/table-edit",
            {"values": {"published_at": at(10).isoformat()}},
            format="json",
        )

    assert response.status_code == 400


def test_calendar_rows_say_whether_they_may_change(article_calendar, client):
    Article.objects.create(title="A", published_at=at(3))
    Article.objects.create(title="B", published_at=at(4))

    def refuse_b(self, request, obj=None):
        return obj is None or obj.title != "B"

    with mock.patch.object(ArticleAdmin, "has_change_permission", refuse_b):
        rows = month(client).json()["results"]

    assert {row["title"]: row["__can_change__"] for row in rows} == {
        "A": True,
        "B": False,
    }


def test_rescheduling_goes_through_publishing(story_calendar, client):
    story = Story.objects.create(
        title="Soon", published_at=timezone.now() + timedelta(days=2)
    )
    later = timezone.now() + timedelta(days=5)

    response = client.post(
        f"{STORIES}/{story.pk}/publishing",
        {"action": "schedule", "at": later.isoformat()},
        format="json",
    )

    assert response.status_code == 200
    story.refresh_from_db()
    assert abs((story.published_at - later).total_seconds()) < 1


# Checks


def _errors(views, studio_model=Article):
    class Studio(ModelStudio):
        list_views = views

    return list_config_errors(Studio(studio_model, admin_site))


def test_calendar_views_validate():
    assert _errors(["table", "list", CalendarView("published_at")]) == []


def test_unknown_views_are_rejected():
    errors = _errors(["table", "board"])

    assert errors[0][0] == "content_studio.E002"
    assert "'board'" in errors[0][1]


def test_bare_calendar_needs_publishing():
    errors = _errors(["calendar"])

    assert [error[0] for error in errors] == ["content_studio.E059"]


def test_bare_calendar_with_publishing_validates():
    class Studio(ModelStudio):
        list_views = ["calendar"]
        publishing = "published_at"

    assert list_config_errors(Studio(Story, admin_site)) == []


def test_calendar_field_must_be_a_date():
    errors = _errors([CalendarView("title")])

    assert [error[0] for error in errors] == ["content_studio.E060"]
    assert "not a DateField" in errors[0][1]


def test_calendar_field_must_exist():
    errors = _errors([CalendarView("launch", end="views")])

    assert [error[0] for error in errors] == [
        "content_studio.E060",
        "content_studio.E060",
    ]


def test_two_calendars_of_one_field_are_rejected():
    errors = _errors([CalendarView("published_at"), CalendarView("published_at")])

    assert [error[0] for error in errors] == ["content_studio.E060"]
    assert "two calendars" in errors[0][1]
