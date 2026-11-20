"""
Tests for view_on_site: the URL of the edit page's "View on site" button
on detail responses, the studio's switches and the system check.
"""

import pytest
from django.contrib.auth.models import User
from rest_framework.test import APIClient

from content_studio.admin import ModelStudio
from content_studio.checks import check_content_studio, view_on_site_errors
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.admin import ArticleAdmin
from tests.testapp.models import Article

ARTICLES = "/api/content/testapp.article"


@pytest.fixture
def client():
    user = User.objects.create_superuser(username="admin", password="x")
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return api


@pytest.fixture
def article(monkeypatch):
    monkeypatch.setattr(
        Article,
        "get_absolute_url",
        lambda self: f"/articles/{self.pk}/",
        raising=False,
    )
    return Article.objects.create(title="Hello")


@pytest.mark.django_db
def test_detail_carries_get_absolute_url(client, article):
    response = client.get(f"{ARTICLES}/{article.pk}")

    assert response.status_code == 200
    assert response.data["__view_on_site__"] == f"/articles/{article.pk}/"


@pytest.mark.django_db
def test_no_url_without_get_absolute_url(client):
    article = Article.objects.create(title="Hello")

    response = client.get(f"{ARTICLES}/{article.pk}")

    assert response.data["__view_on_site__"] is None


@pytest.mark.django_db
def test_list_rows_leave_it_out(client, article):
    response = client.get(ARTICLES)

    assert "__view_on_site__" not in response.data["results"][0]


@pytest.mark.django_db
def test_false_hides_it(client, article, monkeypatch):
    monkeypatch.setattr(ArticleAdmin, "view_on_site", False)

    response = client.get(f"{ARTICLES}/{article.pk}")

    assert response.data["__view_on_site__"] is None


@pytest.mark.django_db
def test_a_method_returns_the_url(client, article, monkeypatch):
    def view_on_site(self, obj):
        return None if obj.title == "Draft" else f"https://example.com/{obj.pk}"

    monkeypatch.setattr(ArticleAdmin, "view_on_site", view_on_site)

    response = client.get(f"{ARTICLES}/{article.pk}")
    assert response.data["__view_on_site__"] == f"https://example.com/{article.pk}"

    draft = Article.objects.create(title="Draft")
    response = client.get(f"{ARTICLES}/{draft.pk}")
    assert response.data["__view_on_site__"] is None


@pytest.mark.django_db
def test_get_link_url_is_the_default(client, article, monkeypatch):
    # Headless sites point rich text links elsewhere; the button follows.
    monkeypatch.setattr(
        ArticleAdmin,
        "get_link_url",
        lambda self, obj: f"https://www.example.com/a/{obj.pk}",
    )

    response = client.get(f"{ARTICLES}/{article.pk}")

    assert (
        response.data["__view_on_site__"] == f"https://www.example.com/a/{article.pk}"
    )


@pytest.mark.django_db
def test_saving_returns_the_new_url(client, monkeypatch):
    monkeypatch.setattr(
        Article,
        "get_absolute_url",
        lambda self: f"/articles/{self.title.lower()}/",
        raising=False,
    )
    article = Article.objects.create(title="Old")

    response = client.patch(f"{ARTICLES}/{article.pk}", {"title": "New"}, format="json")

    assert response.status_code == 200
    assert response.data["__view_on_site__"] == "/articles/new/"


def test_the_check_accepts_booleans_and_methods():
    class Plain(ModelStudio):
        pass

    class Off(ModelStudio):
        view_on_site = False

    class Method(ModelStudio):
        def view_on_site(self, obj):
            return "/"

    for studio in (Plain, Off, Method):
        assert view_on_site_errors(studio(Article, None)) == []


def test_the_check_refuses_anything_else(monkeypatch):
    monkeypatch.setattr(ArticleAdmin, "view_on_site", "/articles/")

    errors = [m for m in check_content_studio() if m.id == "content_studio.E045"]

    assert len(errors) == 1
    assert "view_on_site" in errors[0].msg


@pytest.mark.django_db
@pytest.mark.parametrize(
    "url",
    [
        "javascript:alert(document.domain)",
        " JavaScript:alert(1)",
        "java\tscript:alert(1)",
        "data:text/html,<script>alert(1)</script>",
        "//evil.example/",
    ],
)
def test_urls_that_would_run_a_script_are_dropped(client, article, monkeypatch, url):
    monkeypatch.setattr(ArticleAdmin, "view_on_site", lambda self, obj: url)

    response = client.get(f"{ARTICLES}/{article.pk}")

    assert response.data["__view_on_site__"] is None


@pytest.mark.parametrize(
    "url",
    ["/articles/1/", "https://example.com/a", "http://example.com", "a/b?c=d:e"],
)
def test_safe_urls_are_kept(url):
    from content_studio.utils import safe_link_url

    assert safe_link_url(url) == url
