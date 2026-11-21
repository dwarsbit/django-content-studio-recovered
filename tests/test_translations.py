"""
Tests for translated content (ModelStudio.translations): the adapters,
the API's per-language columns, required languages, the list's
language states, the Missing translation filter, search, prepopulated
fields and the checks (E055, W030).
"""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory, override_settings
from rest_framework.test import APIClient

from content_studio.admin import (
    AdminSerializer,
    admin_site,
    get_form_field_names,
    serialize_prepopulated_fields,
)
from content_studio.checks import translation_errors, translation_warnings
from content_studio.filters import get_filter_specs
from content_studio.serializers import ModelSerializer
from content_studio.token_backends.jwt import create_access_token
from content_studio.translations import (
    ColumnsAdapter,
    ModelTranslationAdapter,
    ParlerAdapter,
    Translations,
    build_translation_config,
    detect_adapter,
    get_content_languages,
    get_search_fields,
    translated_attribute_names,
)
from tests.testapp.models import Article, Guide

GUIDES = "/api/content/testapp.guide"


def studio():
    return admin_site._registry[Guide]


@pytest.fixture
def user(db):
    return User.objects.create_superuser(username="admin", password="x")


@pytest.fixture
def client(user):
    api = APIClient()
    api.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return api


@pytest.fixture
def request_(user):
    request = RequestFactory().get("/")
    request.user = user
    return request


# Languages and config


def test_content_languages_default_first():
    assert get_content_languages() == [
        ("en", "English"),
        ("nl", "Dutch"),
        ("de", "German"),
    ]


@override_settings(
    CONTENT_STUDIO={"CONTENT_LANGUAGES": None},
    LANGUAGE_CODE="nl",
    LANGUAGES=[("en", "English"), ("nl", "Dutch")],
)
def test_without_content_languages_languages_with_language_code_first():
    assert get_content_languages() == [("nl", "Dutch"), ("en", "English")]


def test_columns_config():
    config = build_translation_config(studio())

    assert config.default == "en"
    assert config.required == ["en"]
    assert config.columns()["title"] == {
        "en": "title",
        "nl": "title_nl",
        "de": "title_de",
    }
    assert config.serialize()["fields"]["body"]["de"] == "body_de"


def test_translations_object_narrows_languages_and_required():
    with mock.patch.object(
        studio(),
        "translations",
        Translations(["title"], languages=["en", "de"], required=["en", "de"]),
    ):
        config = build_translation_config(studio())

    assert list(config.columns()) == ["title"]
    assert config.columns()["title"] == {"en": "title", "de": "title_de"}
    assert config.required == ["en", "de"]


def test_studios_without_translations_have_no_config():
    assert build_translation_config(admin_site._registry[Article]) is None


# The API


@pytest.mark.django_db
def test_every_language_is_written_and_read(client):
    response = client.post(
        GUIDES,
        {"title": "Hello", "title_nl": "Hallo", "title_de": "", "views": 2},
        format="json",
    )

    assert response.status_code == 201, response.data
    guide = Guide.objects.get(pk=response.data["id"])
    assert (guide.title, guide.title_nl, guide.title_de) == ("Hello", "Hallo", "")

    response = client.patch(
        f"{GUIDES}/{guide.pk}", {"title_de": "Hallo DE"}, format="json"
    )

    assert response.status_code == 200
    assert response.data["title_de"] == "Hallo DE"


@pytest.mark.django_db
def test_required_language_must_be_filled(client):
    response = client.post(GUIDES, {"title": "", "title_nl": "Hallo"}, format="json")

    assert response.status_code == 400
    assert "title" in response.data


@pytest.mark.django_db
def test_other_languages_may_stay_empty(client):
    response = client.post(GUIDES, {"title": "Hello"}, format="json")

    assert response.status_code == 201


@pytest.mark.django_db
def test_required_other_language(client):
    with mock.patch.object(
        studio(), "translations", Translations(["title"], required=["en", "nl"])
    ):
        response = client.post(GUIDES, {"title": "Hello"}, format="json")

    assert response.status_code == 400
    assert "title_nl" in response.data


@pytest.mark.django_db
def test_list_rows_carry_columns_and_missing_counts(client):
    Guide.objects.create(title="Hello", title_nl="Hallo", body="Text")

    row = client.get(GUIDES).data["results"][0]

    assert row["title_nl"] == "Hallo"
    assert row["title_de"] == ""
    # Missing: nl lacks body; de lacks title and body. slug is empty in all.
    assert row["__languages__"] == {"en": 1, "nl": 2, "de": 3}


@pytest.mark.django_db
def test_missing_translation_filter(client):
    complete = Guide.objects.create(
        title="A",
        title_nl="A",
        title_de="A",
        slug="a",
        slug_nl="a",
        slug_de="a",
        body="a",
        body_nl="a",
        body_de="a",
    )
    no_german = Guide.objects.create(
        title="B", title_nl="B", slug="b", slug_nl="b", body="b", body_nl="b"
    )

    def ids(**params):
        return [row["id"] for row in client.get(GUIDES, params).data["results"]]

    assert ids(missing_translation="de") == [no_german.pk]
    assert ids(missing_translation="nl") == []
    assert sorted(ids()) == sorted([complete.pk, no_german.pk])


def test_missing_translation_filter_is_added_and_offers_optional_languages(
    request_,
):
    specs = [spec for spec in get_filter_specs(studio()) if hasattr(spec, "filter")]
    names = [getattr(spec, "name", None) for spec in specs]

    assert "missing_translation" in names

    spec = specs[names.index("missing_translation")]
    assert spec.filter.get_options(request_) == [("nl", "Dutch"), ("de", "German")]


@pytest.mark.django_db
def test_search_finds_every_language(client):
    guide = Guide.objects.create(title="Hello", title_de="Guten Tag")

    results = client.get(GUIDES, {"search": "Guten"}).data["results"]

    assert [row["id"] for row in results] == [guide.pk]


def test_search_fields_expand_with_prefix():
    with mock.patch.object(studio(), "search_fields", ["^title", "views"]):
        assert get_search_fields(studio()) == [
            "^title",
            "^title_nl",
            "^title_de",
            "views",
        ]


def test_form_field_names_include_every_language(request_):
    names = get_form_field_names(studio(), request_)

    assert {"title", "title_nl", "title_de", "body_de", "views"} <= names


def test_default_layout_leaves_out_language_columns(request_):
    fields = studio().get_fields(request_)

    assert "title" in fields
    assert "title_nl" not in fields
    assert "body_de" not in fields


def test_slug_follows_the_title_in_its_language(request_):
    assert serialize_prepopulated_fields(studio(), request_) == {
        "slug": ["title"],
        "slug_nl": ["title_nl"],
        "slug_de": ["title_de"],
    }


def test_model_info_labels_columns_with_their_language(request_):
    fields = ModelSerializer(Guide).serialize()["fields"]

    assert fields["title_nl"]["verbose_name"] == "title (Dutch)"
    assert fields["title"]["verbose_name"] == "title (English)"
    assert fields["title"]["required"] is True
    assert fields["title_nl"]["required"] is False

    admin = AdminSerializer(studio()).serialize(request_)
    assert admin["translations"]["default"] == "en"
    assert admin["translations"]["languages"][1] == {"code": "nl", "name": "Dutch"}


# Adapter detection


def test_plain_models_use_the_columns_adapter():
    assert detect_adapter(Guide) is None
    assert isinstance(build_translation_config(studio()).adapter, ColumnsAdapter)


def test_modeltranslation_is_detected_by_its_fields():
    proxy = SimpleNamespace(name="title")
    column = SimpleNamespace(
        name="title_en", translated_field=proxy, language="en"
    )
    model = SimpleNamespace(
        _meta=SimpleNamespace(get_fields=lambda: [proxy, column])
    )

    assert detect_adapter(model) is ModelTranslationAdapter


def test_parler_is_detected_by_its_meta():
    meta = SimpleNamespace(get_all_fields=lambda: ["title", "summary"])
    model = SimpleNamespace(
        _parler_meta=meta, _meta=SimpleNamespace(get_fields=lambda: [])
    )

    assert detect_adapter(model) is ParlerAdapter
    assert translated_attribute_names(model) == {"title", "summary"}
    assert translated_attribute_names(Guide) == set()


def test_parler_columns_cannot_clash_with_model_fields():
    adapter = ParlerAdapter(Guide, Translations(["title"]))

    assert adapter.column("title", "pt-BR", "en") == "title__pt_br"


# Checks


def check_ids(function, translations):
    with mock.patch.object(studio(), "translations", translations):
        return [check_id for check_id, _ in function(studio())]


def test_valid_translations_pass_the_checks():
    assert translation_errors(studio()) == []
    assert translation_warnings(studio()) == []


@pytest.mark.parametrize(
    "translations",
    [
        "title",
        ["title", 3],
        ["missing"],
        Translations(["title"], languages=["fr"]),
        Translations(["title"], required=["fr"]),
        Translations(["title"], adapter="unknown"),
        Translations(["title"], adapter=object),
    ],
)
def test_malformed_translations_are_e054(translations):
    assert check_ids(translation_errors, translations) == ["content_studio.E055"]


def test_field_without_a_column_for_a_language_is_w030():
    ids = check_ids(translation_warnings, ["title", "views"])

    assert ids == ["content_studio.W030"]
