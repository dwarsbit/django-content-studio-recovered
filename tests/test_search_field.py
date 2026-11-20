"""
The search field a relation picker fills with the typed text when it
creates an object (get_search_field, in the admin's list metadata).
"""

import pytest
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from rest_framework.test import APIRequestFactory

from content_studio.admin import (
    AdminSerializer,
    ModelStudio,
    admin_site,
    get_search_field,
)
from tests.testapp.models import Article, Category


def studio(model, search_fields):
    return type("Studio", (ModelStudio,), {"search_fields": search_fields})(model, None)


def test_first_search_field_when_it_is_a_text_field():
    assert get_search_field(studio(Category, ["name"])) == "name"
    assert get_search_field(studio(get_user_model(), ["username", "email"])) == (
        "username"
    )


def test_none_without_search_fields():
    assert get_search_field(studio(Category, [])) is None


def test_none_for_a_path_across_relations():
    assert get_search_field(studio(Article, ["author__username"])) is None


def test_none_for_a_field_that_is_not_text():
    assert get_search_field(studio(Article, ["views"])) is None
    assert get_search_field(studio(Article, ["status"])) is None


def test_none_for_an_unknown_field():
    assert get_search_field(studio(Group, ["missing"])) is None


@pytest.mark.django_db
def test_admin_metadata_names_the_search_field():
    user = get_user_model().objects.create_superuser(username="admin", password="x")
    request = APIRequestFactory().get("/")
    request.user = user

    serialized = AdminSerializer(admin_site._registry[Category]).serialize(request)

    assert serialized["list"]["search_field"] == "name"
