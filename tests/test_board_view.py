"""
Tests for the board list view (content_studio.list_views.BoardView): the
config and its columns, the board endpoint (counts, first cards, "Show
more", one column, search and filters), saving a dragged card through
the table edit save, and the checks (E002, E061).
"""

from unittest import mock

import pytest
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, admin_site
from content_studio.checks import list_config_errors
from content_studio.list_views import (
    BOARD_PAGE_SIZE,
    BoardView,
    get_drag_fields,
)
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.admin import ArticleAdmin
from tests.testapp.models import Article

ARTICLES = "/api/content/testapp.article"


def api_for(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return api


@pytest.fixture
def user(db):
    return User.objects.create_superuser(
        username="admin", password="x", first_name="Ada", last_name="Admin"
    )


@pytest.fixture
def client(user):
    return api_for(user)


@pytest.fixture
def request_(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


@pytest.fixture
def status_board():
    """Articles on a board of their status."""
    with mock.patch.object(ArticleAdmin, "list_views", ["table", BoardView("status")]):
        yield


@pytest.fixture
def author_board():
    """Articles on a board of their author (a nullable foreign key)."""
    with mock.patch.object(ArticleAdmin, "list_views", ["table", BoardView("author")]):
        yield


def staff(*codenames):
    user = User.objects.create_user(username="staff", password="x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


def views_for(request):
    return AdminSerializer(ArticleAdmin(Article, admin_site)).serialize(request)[
        "list"
    ]["views"]


def board(client, **params):
    return client.get(f"{ARTICLES}/board", {"view": "board:status", **params})


def by_value(response):
    return {column["value"]: column for column in response.json()["columns"]}


# Config and metadata


def test_board_of_a_choice_field(status_board, request_):
    view = views_for(request_)[1]

    assert view == {
        "type": "board",
        "key": "board:status",
        "field": "status",
        "label": "Status",
        "relation": False,
        "empty_value": "",
        "columns": [
            {"value": "draft", "label": "Draft"},
            {"value": "published", "label": "Published"},
        ],
        "editable": True,
    }


def test_columns_pick_and_order_the_choices(request_):
    with mock.patch.object(
        ArticleAdmin,
        "list_views",
        [BoardView("status", columns=["published", "draft"], label="Stage")],
    ):
        view = views_for(request_)[0]

    assert view["label"] == "Stage"
    assert [column["value"] for column in view["columns"]] == ["published", "draft"]


def test_board_of_a_foreign_key(author_board, user, request_):
    other = User.objects.create_user(username="zed", password="x", is_staff=True)

    view = views_for(request_)[1]

    assert view["relation"] is True
    # Items without an author first, then the users the picker offers.
    assert view["columns"][0] == {"value": None, "label": ""}
    assert {column["value"] for column in view["columns"][1:]} == {
        user.pk,
        other.pk,
    }


def test_foreign_key_columns_pick_objects(user, request_):
    other = User.objects.create_user(username="zed", password="x")

    with mock.patch.object(
        ArticleAdmin, "list_views", [BoardView("author", columns=[other.pk])]
    ):
        view = views_for(request_)[0]

    assert [column["value"] for column in view["columns"]] == [None, other.pk]


def test_not_editable_without_change_permission(status_board, db):
    request = RequestFactory().get("/")
    request.user = staff("view_article")

    assert views_for(request)[1]["editable"] is False
    assert get_drag_fields(ArticleAdmin(Article, admin_site), request) == []


def test_editable_false_opts_out(request_):
    with mock.patch.object(
        ArticleAdmin, "list_views", [BoardView("status", editable=False)]
    ):
        assert views_for(request_)[0]["editable"] is False
        assert get_drag_fields(ArticleAdmin(Article, admin_site), request_) == []


def test_board_field_is_a_drag_field(status_board, request_):
    assert get_drag_fields(ArticleAdmin(Article, admin_site), request_) == ["status"]


# The board endpoint


def test_columns_with_counts_and_cards(status_board, client):
    Article.objects.create(title="One", status="draft")
    Article.objects.create(title="Two", status="draft")
    Article.objects.create(title="Live", status="published")

    response = board(client)

    assert response.status_code == 200, response.json()
    columns = by_value(response)
    assert columns["draft"]["count"] == 2
    assert columns["draft"]["label"] == "Draft"
    assert [row["title"] for row in columns["draft"]["results"]] == ["One", "Two"]
    assert [row["title"] for row in columns["published"]["results"]] == ["Live"]
    # Rows carry the board field, their card and whether they may change.
    row = columns["published"]["results"][0]
    assert row["status"] == "published"
    assert row["list_item_display"]["title"] == "Live"
    assert row["__can_change__"] is True


def test_search_and_filters_apply(status_board, client):
    Article.objects.create(title="Apple", status="draft")
    Article.objects.create(title="Banana", status="draft")
    Article.objects.create(title="Apple pie", status="published")

    searched = by_value(board(client, search="apple"))
    assert searched["draft"]["count"] == 1
    assert searched["published"]["count"] == 1

    filtered = by_value(board(client, status="published"))
    assert filtered["draft"]["count"] == 0
    assert filtered["published"]["count"] == 1


def test_ordering_applies(status_board, client):
    Article.objects.create(title="B", status="draft")
    Article.objects.create(title="A", status="draft")

    columns = by_value(board(client, ordering="title"))

    assert [row["title"] for row in columns["draft"]["results"]] == ["A", "B"]


def test_columns_show_a_page_and_more_on_request(status_board, client):
    for index in range(BOARD_PAGE_SIZE + 2):
        Article.objects.create(title=f"Draft {index}", status="draft")

    first = by_value(board(client))["draft"]
    assert first["count"] == BOARD_PAGE_SIZE + 2
    assert len(first["results"]) == BOARD_PAGE_SIZE

    more = by_value(board(client, show="draft:40"))["draft"]
    assert len(more["results"]) == BOARD_PAGE_SIZE + 2


def test_one_column_with_an_offset(status_board, client):
    for index in range(3):
        Article.objects.create(title=f"Draft {index}", status="draft")

    response = board(client, column="draft", offset=1)

    assert response.status_code == 200
    assert response.json()["count"] == 3
    assert [row["title"] for row in response.json()["results"]] == [
        "Draft 1",
        "Draft 2",
    ]


def test_items_without_a_value(author_board, user, client):
    Article.objects.create(title="Mine", author=user)
    Article.objects.create(title="Nobody's")

    response = client.get(f"{ARTICLES}/board", {"view": "board:author"})
    columns = by_value(response)

    assert [row["title"] for row in columns[None]["results"]] == ["Nobody's"]
    assert columns[user.pk]["count"] == 1
    # Labelled as the author picker shows them.
    assert columns[user.pk]["label"] == "admin"

    none = client.get(
        f"{ARTICLES}/board", {"view": "board:author", "column": "__none__"}
    )
    assert [row["title"] for row in none.json()["results"]] == ["Nobody's"]


def test_a_bad_column_value_is_a_400(author_board, client):
    response = client.get(
        f"{ARTICLES}/board", {"view": "board:author", "column": "nope"}
    )

    assert response.status_code == 400


def test_no_board_is_a_404(client):
    assert board(client).status_code == 404


def test_the_board_needs_view_permission(status_board, db):
    response = board(api_for(staff()))

    assert response.status_code == 403


# Dragging


def test_drag_saves_the_value_through_table_edit(status_board, client):
    article = Article.objects.create(title="Move me", status="draft")

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {"values": {"status": "published"}, "base": {"status": "draft"}},
        format="json",
    )

    assert response.status_code == 200, response.json()
    article.refresh_from_db()
    assert article.status == "published"


def test_drag_of_a_foreign_key(author_board, user, client):
    article = Article.objects.create(title="Claim me")

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {"values": {"author": {"id": user.pk}}, "base": {"author": None}},
        format="json",
    )

    assert response.status_code == 200, response.json()
    article.refresh_from_db()
    assert article.author == user


def test_drag_refuses_a_changed_value(status_board, client):
    article = Article.objects.create(title="Moved", status="published")

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {"values": {"status": "draft"}, "base": {"status": "draft"}},
        format="json",
    )

    assert response.status_code == 409


def test_drag_is_refused_without_a_board(client, db):
    article = Article.objects.create(title="Stay", status="draft")

    response = client.post(
        f"{ARTICLES}/{article.pk}/table-edit",
        {"values": {"status": "published"}},
        format="json",
    )

    assert response.status_code == 400


# Checks


def test_board_objects_are_known_views():
    class Studio(ArticleAdmin):
        list_views = ["table", BoardView("status")]

    assert list_config_errors(Studio(Article, admin_site)) == []


@pytest.mark.parametrize(
    "view, message",
    [
        (BoardView("title"), "neither a field with choices nor a ForeignKey"),
        (BoardView("nope"), "is not a field"),
        (BoardView("categories"), "neither a field with choices nor a ForeignKey"),
        (BoardView("status", columns=["archived"]), "'archived'"),
        (BoardView("status", columns=[]), "non-empty list"),
    ],
)
def test_board_checks(view, message):
    class Studio(ArticleAdmin):
        list_views = ["table", view]

    errors = list_config_errors(Studio(Article, admin_site))

    assert [error[0] for error in errors] == ["content_studio.E061"]
    assert message in errors[0][1]


def test_two_boards_of_one_field():
    class Studio(ArticleAdmin):
        list_views = [BoardView("status"), BoardView("status", label="Again")]

    errors = list_config_errors(Studio(Article, admin_site))

    assert [error[0] for error in errors] == ["content_studio.E061"]
