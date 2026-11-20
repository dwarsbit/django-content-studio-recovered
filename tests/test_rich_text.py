"""
Tests for rich text references: render_rich_text and the rich_text
template filter keep the URLs of media library images and of links to
other objects up to date; the link picker searches linkable models; the
sanitizer keeps the references; the system check warns about options
that cannot work.
"""

import pytest
from django.contrib.auth import models as auth_models
from django.core.files.base import ContentFile
from django.template import Context, Template
from django.test import override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from content_studio import widgets
from content_studio.admin import AdminSerializer, admin_site, is_linkable
from content_studio.checks import rich_text_widget_warnings
from content_studio.form import Field
from content_studio.media_library.models import Media
from content_studio.rich_text import render_rich_text
from content_studio.sanitizers import sanitize_html
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article, Category, Note

SETTINGS = {
    "ADMIN_SITE": "content_studio.admin.admin_site",
    "MEDIA_LIBRARY_MODEL": "content_studio.media_library.models.Media",
    "MEDIA_LIBRARY_FOLDER_MODEL": "content_studio.media_library.models.Folder",
}


@pytest.fixture
def media_library(tmp_path):
    with override_settings(MEDIA_ROOT=str(tmp_path), CONTENT_STUDIO=SETTINGS):
        yield


@pytest.fixture
def category_urls(monkeypatch):
    monkeypatch.setattr(
        Category,
        "get_absolute_url",
        lambda self: f"/categories/{self.name.lower()}/",
        raising=False,
    )


def make_image(name="photo.png", **fields):
    return Media.objects.create(
        type="image",
        file=ContentFile(b"not really a png", name=name),
        metadata={"width": 400, "height": 200},
        **fields,
    )


@pytest.mark.django_db
def test_image_gets_current_url_and_size(media_library):
    item = make_image()
    html = (
        '<figure class="rich-text-figure align-left">'
        f'<img src="/old.png" alt="A &amp; B" data-media-id="{item.pk}" '
        'data-size="original"><figcaption>Caption &amp; more</figcaption>'
        "</figure>"
    )

    result = render_rich_text(html)

    assert f'src="{item.file.url}"' in result
    assert 'width="400" height="200"' in result
    assert 'alt="A &amp; B"' in result
    assert "<figcaption>Caption &amp; more</figcaption>" in result
    assert result.startswith('<figure class="rich-text-figure align-left">')


@pytest.mark.django_db
def test_unknown_size_falls_back_to_the_original(media_library):
    item = make_image()

    result = render_rich_text(
        f'<img src="/old.png" data-media-id="{item.pk}" data-size="gone">'
    )

    assert f'src="{item.file.url}"' in result


@pytest.mark.django_db
def test_deleted_image_is_left_as_is(media_library):
    html = '<p>Before</p><img src="/old.png" data-media-id="999"><p>After</p>'

    assert render_rich_text(html) == html


@pytest.mark.django_db
def test_link_gets_current_url(category_urls):
    category = Category.objects.create(name="Travel")
    html = (
        f'<p>See <a href="/old/" data-link-model="testapp.category" '
        f'data-link-id="{category.pk}" target="_blank">travel</a>.</p>'
    )

    result = render_rich_text(html)

    assert (
        '<a href="/categories/travel/" data-link-model="testapp.category" '
        f'data-link-id="{category.pk}" target="_blank">travel</a>'
    ) in result


@pytest.mark.django_db
def test_link_to_deleted_object_keeps_its_text(category_urls):
    html = (
        '<p>See <a href="/old/" data-link-model="testapp.category" '
        'data-link-id="999"><strong>travel</strong></a> and '
        '<a href="https://example.com">this</a>.</p>'
    )

    assert render_rich_text(html) == (
        '<p>See <strong>travel</strong> and <a href="https://example.com">this</a>.</p>'
    )


@pytest.mark.django_db
def test_link_to_trashed_object_keeps_its_text(monkeypatch):
    monkeypatch.setattr(Note, "get_absolute_url", lambda self: "/n/", raising=False)
    note = Note.objects.create(title="Gone", removed_at=timezone.now())
    html = (
        f'<a href="/n/" data-link-model="testapp.note" data-link-id="{note.pk}">x</a>'
    )

    assert render_rich_text(html) == "x"


@pytest.mark.django_db
def test_link_to_unknown_model_is_left_as_is():
    html = '<a href="/x/" data-link-model="nope.model" data-link-id="1">x</a>'

    assert render_rich_text(html) == html


@pytest.mark.django_db
def test_studio_get_link_url_wins(monkeypatch):
    category = Category.objects.create(name="Food")
    studio = admin_site._registry[Category]
    monkeypatch.setattr(
        type(studio),
        "get_link_url",
        lambda self, obj: f"https://site.example/c/{obj.pk}",
    )

    result = render_rich_text(
        f'<a href="/" data-link-model="testapp.category" data-link-id="{category.pk}">x</a>'
    )

    assert f'href="https://site.example/c/{category.pk}"' in result
    assert is_linkable(studio)


def test_plain_html_is_returned_untouched():
    html = "<p>Fish &amp; chips<br/><!-- note --></p>"

    assert render_rich_text(html) == html
    assert render_rich_text("") == ""
    assert render_rich_text(None) == ""


@pytest.mark.django_db
def test_template_filter_sanitizes_and_refreshes(category_urls):
    category = Category.objects.create(name="Travel")
    template = Template("{% load content_studio %}{{ body|rich_text }}")
    body = (
        f'<a href="/old/" data-link-model="testapp.category" data-link-id="{category.pk}">'
        "go</a><script>alert(1)</script>"
    )

    result = template.render(Context({"body": body}))

    assert 'href="/categories/travel/"' in result
    assert "<script>" not in result
    assert template.render(Context({"body": None})) == ""


def test_sanitizer_keeps_references():
    html = (
        '<figure class="rich-text-figure align-wide">'
        '<img src="/a.png" alt="" data-media-id="7" data-size="hero"></figure>'
        '<a href="/x/" data-link-model="blog.article" data-link-id="3">x</a>'
        "<table><tbody><tr><th>a</th></tr><tr><td>b</td></tr></tbody></table>"
    )

    result = sanitize_html(html)

    assert 'data-media-id="7"' in result
    assert 'data-size="hero"' in result
    assert 'data-link-model="blog.article"' in result
    assert 'data-link-id="3"' in result
    assert "<th>a</th>" in result


@pytest.mark.django_db
def test_link_to_a_model_without_a_studio_is_not_resolved(monkeypatch):
    monkeypatch.setattr(
        auth_models.Permission,
        "get_absolute_url",
        lambda self: "/secret/",
        raising=False,
    )
    permission = auth_models.Permission.objects.first()
    html = (
        f'<a href="/x/" data-link-model="auth.permission" '
        f'data-link-id="{permission.pk}">x</a>'
    )

    assert render_rich_text(html) == html


def link_to(category):
    return (
        f'<p><a href="/c/" data-link-model="testapp.category" '
        f'data-link-id="{category.pk}">c</a></p>'
    )


def editor_client(*codenames):
    user = auth_models.User.objects.create_user(
        username="editor", password="x", is_staff=True
    )
    user.user_permissions.set(
        auth_models.Permission.objects.filter(codename__in=codenames)
    )
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.mark.django_db
def test_saving_a_link_to_an_object_the_editor_cannot_see_is_refused(category_urls):
    category = Category.objects.create(name="Hidden")
    client = editor_client("view_article", "add_article", "change_article")

    response = client.post(
        "/api/content/testapp.article",
        {"title": "Linked", "body": link_to(category)},
        format="json",
    )

    assert response.status_code == 400, response.content
    assert "body" in response.json()
    assert not Article.objects.exists()


@pytest.mark.django_db
def test_saving_a_link_the_editor_may_see(category_urls):
    category = Category.objects.create(name="Open")
    client = editor_client(
        "view_article", "add_article", "change_article", "view_category"
    )

    response = client.post(
        "/api/content/testapp.article",
        {"title": "Linked", "body": link_to(category)},
        format="json",
    )

    assert response.status_code == 201, response.content


@pytest.mark.django_db
def test_links_already_in_the_text_are_kept(category_urls):
    category = Category.objects.create(name="Hidden")
    article = Article.objects.create(title="Linked", body=link_to(category))
    client = editor_client("view_article", "change_article")

    response = client.patch(
        f"/api/content/testapp.article/{article.pk}",
        {"body": link_to(category) + "<p>More</p>"},
        format="json",
    )

    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_links_to_unknown_models_are_refused_on_save():
    client = editor_client("view_article", "add_article")

    response = client.post(
        "/api/content/testapp.article",
        {
            "title": "Linked",
            "body": '<a href="/" data-link-model="auth.user" data-link-id="1">x</a>',
        },
        format="json",
    )

    assert response.status_code == 400


def client_for_superuser():
    user = auth_models.User.objects.create_superuser(username="admin", password="x")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.mark.django_db
def test_link_search_offers_only_linkable_models(category_urls):
    Category.objects.create(name="Needle category")
    Article.objects.create(title="Needle article")
    client = client_for_superuser()

    response = client.get("/api/search", {"search": "needle", "linkable": "1"})

    assert response.status_code == 200
    groups = response.json()
    assert [group["model"] for group in groups] == ["testapp.category"]
    assert groups[0]["results"][0]["url"] == "/categories/needle category/"

    # Narrowed to listed models.
    response = client.get(
        "/api/search",
        {"search": "needle", "linkable": "1", "models": "testapp.article"},
    )
    assert response.json() == []

    # The command palette's search is unchanged.
    response = client.get("/api/search", {"search": "needle"})
    assert {group["model"] for group in response.json()} == {
        "testapp.article",
        "testapp.category",
    }
    assert all("url" not in item for g in response.json() for item in g["results"])


@pytest.mark.django_db
def test_discover_marks_linkable_models(rf, category_urls):
    request = rf.get("/")
    request.user = auth_models.User.objects.create_superuser(username="a", password="x")

    assert AdminSerializer(admin_site._registry[Category]).serialize(request)[
        "linkable"
    ]
    assert not AdminSerializer(admin_site._registry[Article]).serialize(request)[
        "linkable"
    ]


def test_check_warns_about_options_that_cannot_work(monkeypatch):
    studio = admin_site._registry[Article]
    monkeypatch.setattr(
        type(studio),
        "edit_main",
        [
            Field(
                "body",
                widget=widgets.RichTextWidget(
                    features=["image"],
                    link_models=["testapp.nope", "testapp.article"],
                    image_sizes=["huge"],
                ),
            )
        ],
    )

    with override_settings(
        CONTENT_STUDIO={"ADMIN_SITE": "content_studio.admin.admin_site"}
    ):
        messages = [message for _, message in rich_text_widget_warnings(studio)]

    assert any("MEDIA_LIBRARY_MODEL" in m for m in messages)
    assert any("'testapp.nope', which is not a registered model" in m for m in messages)
    assert any("'testapp.article', whose objects have no URL" in m for m in messages)
    assert any("'huge', which is not in IMAGE_SIZES" in m for m in messages)
