"""
Tests for the gallery list view ("gallery" in list_views): its config,
rows carrying their list item thumbnail, and the checks (E002, W033).
"""

from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from rest_framework.test import APIClient

from content_studio.admin import AdminSerializer, admin_site
from content_studio.checks import gallery_warnings, list_config_errors
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.admin import ArticleAdmin
from tests.testapp.models import Article

ARTICLES = "/api/content/testapp.article"


@pytest.fixture
def user(db):
    return User.objects.create_superuser(username="admin", password="x")


@pytest.fixture
def client(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return api


GALLERY_DISPLAY = {
    "title": "title",
    "meta": "get_status_display",
    "thumbnail": "get_cover_url",
}


@pytest.fixture
def gallery():
    with (
        mock.patch.object(ArticleAdmin, "list_views", ["table", "gallery"]),
        mock.patch.object(ArticleAdmin, "list_item_display", GALLERY_DISPLAY),
        mock.patch.object(
            Article,
            "get_cover_url",
            lambda self: f"/media/covers/{self.pk}.webp",
            create=True,
        ),
    ):
        yield


def test_gallery_is_offered(gallery, user):
    request = RequestFactory().get("/")
    request.user = user

    views = AdminSerializer(ArticleAdmin(Article, admin_site)).serialize(request)[
        "list"
    ]["views"]

    assert views == ["table", "gallery"]


def test_rows_carry_their_thumbnail(gallery, client):
    article = Article.objects.create(title="Ferry notes", status="published")

    response = client.get(ARTICLES)

    assert response.status_code == 200
    display = response.json()["results"][0]["list_item_display"]
    assert display["title"] == "Ferry notes"
    assert display["meta"] == "Published"
    assert display["thumbnail"] == f"/media/covers/{article.pk}.webp"


def test_gallery_is_a_known_view():
    class Studio(ArticleAdmin):
        list_views = ["table", "gallery"]

    assert list_config_errors(Studio(Article, admin_site)) == []


def test_gallery_without_a_thumbnail_warns():
    class Studio(ArticleAdmin):
        list_views = ["table", "gallery"]

    warnings = gallery_warnings(Studio(Article, admin_site))

    assert [warning[0] for warning in warnings] == ["content_studio.W033"]


def test_gallery_with_a_thumbnail_does_not_warn():
    class Studio(ArticleAdmin):
        list_views = ["table", "gallery"]
        list_item_display = {"title": "title", "thumbnail": "cover"}

    assert gallery_warnings(Studio(Article, admin_site)) == []


def test_computed_items_do_not_warn():
    class Studio(ArticleAdmin):
        list_views = ["gallery"]

        def get_list_item_display(self, obj, request):
            return super().get_list_item_display(obj, request)

    assert gallery_warnings(Studio(Article, admin_site)) == []


def test_no_gallery_no_warning():
    assert gallery_warnings(ArticleAdmin(Article, admin_site)) == []
