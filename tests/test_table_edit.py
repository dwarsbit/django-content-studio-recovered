"""
Tests for inline editing of the table view (ModelStudio.table_edit, alias
list_editable): the names a request may edit, the list's metadata and row
flags, the table-edit endpoint (permissions, validation, conflicts,
translated columns, the activity log, save hooks) and the checks (E056,
W031).
"""

from unittest import mock

import pytest
from django.contrib.admin.models import LogEntry
from django.contrib.auth.models import Permission, User
from django.test import RequestFactory
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, admin_site
from content_studio.checks import table_edit_errors, table_edit_warnings
from content_studio.table_edit import cell_field_error, declared_table_edit
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.admin import ArticleAdmin, GuideAdmin, StoryAdmin
from tests.testapp.models import Article, Guide, Story

ARTICLES = "/api/content/testapp.article"


def studio():
    return admin_site._registry[Article]


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
def editable():
    with mock.patch.object(
        ArticleAdmin, "table_edit", ["title", "status", "published_at"], create=True
    ):
        yield


def staff(*codenames, username="staff"):
    user = User.objects.create_user(username=username, password="x", is_staff=True)
    user.user_permissions.set(Permission.objects.filter(codename__in=codenames))
    return user


def edit(client, obj, values, base=None, url=ARTICLES):
    return client.post(
        f"{url}/{obj.pk}/table-edit",
        {"values": values, **({"base": base} if base is not None else {})},
        format="json",
    )


# Which names a request may edit


def test_off_by_default(request_):
    assert studio().get_table_edit(request_) == []


def test_declared_names(editable, request_):
    assert studio().get_table_edit(request_) == ["title", "status", "published_at"]


def test_list_editable_is_an_alias(request_):
    with mock.patch.object(ArticleAdmin, "list_editable", ["title"], create=True):
        assert declared_table_edit(studio()) == ["title"]
        assert studio().get_table_edit(request_) == ["title"]


def test_table_edit_wins_over_the_alias():
    with (
        mock.patch.object(ArticleAdmin, "list_editable", ["title"], create=True),
        mock.patch.object(ArticleAdmin, "table_edit", ["status"], create=True),
    ):
        assert declared_table_edit(studio()) == ["status"]


def test_fields_the_edit_page_does_not_write_are_left_out(request_):
    # views is a column, but not on ArticleAdmin's edit page.
    with mock.patch.object(ArticleAdmin, "table_edit", ["title", "views"], create=True):
        assert studio().get_table_edit(request_) == ["title"]


def test_readonly_fields_are_left_out(request_):
    with (
        mock.patch.object(ArticleAdmin, "table_edit", ["title", "status"], create=True),
        mock.patch.object(ArticleAdmin, "readonly_fields", ["status"]),
    ):
        assert studio().get_table_edit(request_) == ["title"]


@pytest.mark.django_db
def test_nothing_without_change_permission(editable):
    request = RequestFactory().get("/")
    request.user = staff("view_article")

    assert studio().get_table_edit(request) == []


def test_metadata_lists_the_names(editable, request_):
    data = AdminSerializer(studio()).serialize(request_)

    assert data["list"]["edit"] == ["title", "status", "published_at"]


# List rows


def test_rows_say_whether_they_may_change(editable, client):
    Article.objects.create(title="A")
    Article.objects.create(title="B")

    def refuse_b(self, request, obj=None):
        return obj is None or obj.title != "B"

    with mock.patch.object(ArticleAdmin, "has_change_permission", refuse_b):
        rows = client.get(ARTICLES).json()["results"]

    assert {row["title"]: row["__can_change__"] for row in rows} == {
        "A": True,
        "B": False,
    }


def test_rows_carry_no_flag_without_table_edit(client):
    Article.objects.create(title="A")

    row = client.get(ARTICLES).json()["results"][0]

    assert "__can_change__" not in row


# Saving a cell


def test_saves_a_cell(editable, client, user):
    article = Article.objects.create(title="Old")

    response = edit(client, article, {"title": "New"}, {"title": "Old"})

    assert response.status_code == 200, response.json()
    assert response.json()["values"] == {"title": "New"}
    article.refresh_from_db()
    assert article.title == "New"
    # The save is in the activity log, with the changed field and editor.
    entry = LogEntry.objects.get(object_id=str(article.pk))
    assert entry.user == user
    assert "title" in entry.change_message.lower() or "Title" in entry.change_message
    assert article.edited_by == user


def test_saves_choices_and_dates(editable, client):
    article = Article.objects.create(title="A")

    response = edit(
        client,
        article,
        {"status": "published", "published_at": "2026-01-02T10:00:00Z"},
    )

    assert response.status_code == 200, response.json()
    article.refresh_from_db()
    assert article.status == "published"
    assert article.published_at.year == 2026


def test_validation_errors_per_field(editable, client):
    article = Article.objects.create(title="A")

    response = edit(client, article, {"title": ""})

    assert response.status_code == 400
    assert "title" in response.json()
    article.refresh_from_db()
    assert article.title == "A"


def test_conflict_refuses_the_cell(editable, client):
    article = Article.objects.create(title="Mine")
    Article.objects.filter(pk=article.pk).update(title="Theirs")

    response = edit(client, article, {"title": "New"}, {"title": "Mine"})

    assert response.status_code == 409
    assert set(response.json()["conflicts"]) == {"title"}
    assert response.json()["current"] == {"title": "Theirs"}
    article.refresh_from_db()
    assert article.title == "Theirs"


def test_unchanged_base_is_no_conflict(editable, client, user):
    other = User.objects.create_user(username="other")
    article = Article.objects.create(title="A", author=other)

    with mock.patch.object(ArticleAdmin, "table_edit", ["author"], create=True):
        response = edit(
            client,
            article,
            {"author": {"id": user.pk}},
            {"author": {"id": other.pk, "__str__": "other"}},
        )

    assert response.status_code == 200, response.json()
    article.refresh_from_db()
    assert article.author == user


def test_refuses_names_that_are_not_editable(editable, client):
    article = Article.objects.create(title="A")

    response = edit(client, article, {"body": "x"})

    assert response.status_code == 400
    assert "body" in response.json()


def test_refuses_without_table_edit(client):
    article = Article.objects.create(title="A")

    assert edit(client, article, {"title": "B"}).status_code == 400


def test_refuses_an_empty_edit(editable, client):
    article = Article.objects.create(title="A")

    assert edit(client, article, {}).status_code == 400


@pytest.mark.django_db
def test_needs_change_permission(editable):
    article = Article.objects.create(title="A")
    client = api_for(staff("view_article"))

    assert edit(client, article, {"title": "B"}).status_code == 403


def test_object_permission_is_checked(editable, client):
    article = Article.objects.create(title="A")

    def refuse_objects(self, request, obj=None):
        return obj is None

    with mock.patch.object(ArticleAdmin, "has_change_permission", refuse_objects):
        response = edit(client, article, {"title": "B"})

    assert response.status_code == 403
    article.refresh_from_db()
    assert article.title == "A"


def test_runs_the_save_hooks(editable, client):
    article = Article.objects.create(title="A")
    seen = []

    def save_model(self, request, obj, data, change):
        seen.append((obj.title, change))
        obj.save()

    with mock.patch.object(ArticleAdmin, "save_model", save_model):
        assert edit(client, article, {"title": "B"}).status_code == 200

    assert seen == [("B", True)]


def test_runs_model_validation(editable, client):
    from django.core.exceptions import ValidationError

    article = Article.objects.create(title="A")

    def clean(self):
        if self.title == "Bad":
            raise ValidationError({"title": "Not this title."})

    with mock.patch.object(Article, "clean", clean):
        response = edit(client, article, {"title": "Bad"})

    assert response.status_code == 400
    assert response.json()["title"] == ["Not this title."]


# Translated columns


GUIDES = "/api/content/testapp.guide"


def test_edits_a_language_column(client):
    guide = Guide.objects.create(title="Hello")

    with mock.patch.object(GuideAdmin, "table_edit", ["title"], create=True):
        response = edit(
            client, guide, {"title_nl": "Hallo"}, {"title_nl": ""}, url=GUIDES
        )

    assert response.status_code == 200, response.json()
    guide.refresh_from_db()
    assert (guide.title, guide.title_nl) == ("Hello", "Hallo")


def test_refuses_columns_of_other_fields(client):
    guide = Guide.objects.create(title="Hello")

    with mock.patch.object(GuideAdmin, "table_edit", ["title"], create=True):
        response = edit(client, guide, {"slug_nl": "hallo"}, url=GUIDES)

    assert response.status_code == 400


# Kinds of fields and checks


def test_cell_field_errors():
    article_studio = studio()

    assert cell_field_error(article_studio, "title") is None
    assert cell_field_error(article_studio, "status") is None
    assert cell_field_error(article_studio, "author") is None
    assert cell_field_error(article_studio, "published_at") is None
    assert cell_field_error(article_studio, "rating") is None
    assert "cannot edit" in cell_field_error(article_studio, "categories")
    assert "not a field" in cell_field_error(article_studio, "nope")
    assert "not editable" in cell_field_error(article_studio, "id")


def test_publishing_fields_are_not_cells():
    story_studio = admin_site._registry[Story]

    for name in ("published_at", "unpublish_at", "status"):
        assert "publishing" in cell_field_error(story_studio, name)


def test_check_e056():
    with mock.patch.object(
        ArticleAdmin,
        "table_edit",
        ["title", "body", "categories", "views", 3],
        create=True,
    ):
        errors = table_edit_errors(studio())

    messages = [message for check_id, message in errors]
    assert {check_id for check_id, _ in errors} == {"content_studio.E056"}
    assert any("'body', which is not a table_display column" in m for m in messages)
    assert any("'categories'" in m for m in messages)
    assert any(
        "'views', which is not a field the edit page writes" in m for m in messages
    )
    assert any("must be field names" in m for m in messages)


def test_check_e056_publishing():
    with mock.patch.object(StoryAdmin, "table_edit", ["status"], create=True):
        errors = table_edit_errors(admin_site._registry[Story])

    assert errors and "publishing" in errors[0][1]


def test_check_e056_not_a_list():
    with mock.patch.object(ArticleAdmin, "table_edit", "title", create=True):
        errors = table_edit_errors(studio())

    assert errors == [
        (
            "content_studio.E056",
            "ArticleAdmin.table_edit must be a list of field names.",
        )
    ]


def test_valid_config_passes():
    with mock.patch.object(
        ArticleAdmin, "table_edit", ["title", "status"], create=True
    ):
        assert table_edit_errors(studio()) == []
        assert table_edit_warnings(studio()) == []


def test_check_w031_alias():
    with mock.patch.object(ArticleAdmin, "list_editable", ["title"], create=True):
        warnings = table_edit_warnings(studio())

    assert warnings == [
        (
            "content_studio.W031",
            "ArticleAdmin.list_editable is the Django admin's name for the "
            "columns edited in place; rename it to table_edit.",
        )
    ]


def test_check_w031_without_table_view():
    with (
        mock.patch.object(ArticleAdmin, "table_edit", ["title"], create=True),
        mock.patch.object(ArticleAdmin, "list_views", ["list"]),
    ):
        warnings = table_edit_warnings(studio())

    assert [check_id for check_id, _ in warnings] == ["content_studio.W031"]
    assert "table view" in warnings[0][1]
