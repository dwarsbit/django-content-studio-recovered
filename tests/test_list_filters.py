"""
Custom list filters (ListFilter, Django's SimpleListFilter) and list
filters across relations ("author__username").
"""

import pytest
from django.contrib import admin as django_admin
from django.contrib.auth.models import User
from rest_framework.exceptions import ParseError
from rest_framework.parsers import JSONParser
from rest_framework.request import Request
from rest_framework.test import APIClient, APIRequestFactory

from content_studio.admin import ModelStudio, admin_site
from content_studio.checks import check_content_studio
from content_studio.filters import ListFilter, LookupFilter, serialize_list_filters
from content_studio.token_backends.jwt import create_access_token
from tests.testapp.models import Article, Review


class StubStudio:
    def __init__(self, model, list_filter, exclude=None):
        self.model = model
        self.list_filter = list(list_filter)
        self.exclude = exclude


class StubView:
    action = "list"

    def __init__(self, studio):
        self.queryset = studio.model.objects.none()
        self._admin_model = studio


def make_request(query_string, user=None):
    request = Request(
        APIRequestFactory().get(f"/?{query_string}"), parsers=[JSONParser()]
    )
    if user is not None:
        request.user = user
    return request


def run(model, query_string, list_filter, exclude=None, user=None):
    studio = StubStudio(model, list_filter, exclude)
    return LookupFilter().filter_queryset(
        make_request(query_string, user), model.objects.all(), StubView(studio)
    )


def titles(queryset):
    return set(queryset.values_list("title", flat=True))


@pytest.fixture
def articles(db):
    ann = User.objects.create_user(username="ann", password="x", email="a@x.nl")
    bob = User.objects.create_user(username="bob", password="x", email="b@x.com")
    first = Article.objects.create(title="First", author=ann, views=10)
    Article.objects.create(title="Second", author=bob, views=200)
    Article.objects.create(title="Third", views=3000)
    Review.objects.create(article=first, text="Great", stars=5)
    return {"ann": ann, "bob": bob}


# Filters across relations


@pytest.mark.django_db
def test_filter_across_a_relation(articles):
    result = run(Article, "author__username=ann", ["author__username"])

    assert titles(result) == {"First"}


@pytest.mark.django_db
def test_lookups_of_the_last_field_work(articles):
    result = run(Article, "author__email__endswith=.com", ["author__email"])
    excluded = run(Article, "~author__username=ann", ["author__username"])
    many = run(Article, "author__username=ann,bob", ["author__username"])

    assert titles(result) == {"Second"}
    assert titles(excluded) == {"Second", "Third"}
    assert titles(many) == {"First", "Second"}


@pytest.mark.django_db
def test_filter_across_a_reverse_relation(articles):
    result = run(Article, "review__stars__gte=4", ["review__stars"])

    assert titles(result) == {"First"}


@pytest.mark.parametrize(
    "query",
    [
        # Not declared: only the declared path filters.
        "author__email=a@x.nl",
        "author__is_staff=true",
        # Past the declared path's last field.
        "author__username__icontains__exact=a",
        "author__username__foo=a",
    ],
)
def test_only_declared_paths_and_their_lookups(query):
    with pytest.raises(ParseError):
        run(Article, query, ["author__username"])


@pytest.mark.parametrize(
    "query",
    [
        "author__password__startswith=pbkdf2",
        "author__password=x",
        "~author__password__gt=pbkdf2",
    ],
)
def test_the_password_is_never_filterable_even_when_declared(query):
    with pytest.raises(ParseError) as exc_info:
        run(Article, query, ["author__password"])

    assert "cannot be filtered on" in str(exc_info.value)


def test_excluded_fields_are_never_filterable_even_when_declared():
    with pytest.raises(ParseError) as exc_info:
        run(Article, "body__icontains=secret", ["body"], exclude=["body"])

    assert "cannot be filtered on" in str(exc_info.value)


def test_fields_excluded_by_the_related_studio_are_not_crossed(monkeypatch):
    studio = admin_site._registry[Article]
    monkeypatch.setattr(studio, "exclude", ["body"])

    with pytest.raises(ParseError) as exc_info:
        run(Review, "article__body__icontains=x", ["article__body"])

    assert "cannot be filtered on" in str(exc_info.value)


@pytest.mark.django_db
def test_a_field_list_filter_tuple_filters_on_its_field(articles):
    result = run(
        Article,
        "author__username=bob",
        [("author__username", django_admin.RelatedOnlyFieldListFilter)],
    )

    assert titles(result) == {"Second"}


# Custom filters


class PopularityFilter(ListFilter):
    title = "Popularity"
    parameter_name = "popularity"
    options = [("low", "Low"), ("high", "High")]

    def queryset(self, request, queryset, value):
        if value == "low":
            return queryset.filter(views__lt=100)
        return queryset.filter(views__gte=100)


class SizeFilter(ListFilter):
    title = "Size"
    parameter_name = "size"
    multiple = True

    def get_options(self, request):
        return [(10, "Ten"), (200, "Two hundred"), (3000, "Three thousand")]

    def queryset(self, request, queryset, value):
        return queryset.filter(views__in=[int(v) for v in value])


class OwnFilter(ListFilter):
    """Options and queryset that depend on the request."""

    title = "Mine"
    parameter_name = "mine"

    def get_options(self, request):
        return [("yes", f"By {request.user.username}")]

    def queryset(self, request, queryset, value):
        return queryset.filter(author=request.user)


class DjangoDecadeFilter(django_admin.SimpleListFilter):
    title = "Views"
    parameter_name = "range"

    def lookups(self, request, model_admin):
        return [("small", "Small"), ("large", "Large")]

    def queryset(self, request, queryset):
        if self.value() == "small":
            return queryset.filter(views__lt=1000)
        if self.value() == "large":
            return queryset.filter(views__gte=1000)
        return None


@pytest.mark.django_db
def test_custom_filter(articles):
    assert titles(run(Article, "popularity=low", [PopularityFilter])) == {"First"}
    assert titles(run(Article, "popularity=high", [PopularityFilter])) == {
        "Second",
        "Third",
    }


@pytest.mark.django_db
def test_multiple_choice_custom_filter_receives_a_list(articles):
    result = run(Article, "size=10,3000", [SizeFilter])

    assert titles(result) == {"First", "Third"}


@pytest.mark.django_db
def test_custom_filter_can_use_the_request(articles):
    result = run(Article, "mine=yes", [OwnFilter], user=articles["bob"])

    assert titles(result) == {"Second"}


@pytest.mark.django_db
def test_custom_filters_combine_with_field_filters(articles):
    result = run(
        Article,
        "popularity=high&author__username=bob",
        [PopularityFilter, "author__username"],
    )

    assert titles(result) == {"Second"}


@pytest.mark.parametrize(
    "query",
    [
        # Not an option.
        "popularity=medium",
        # One value only.
        "popularity=low,high",
        # Custom filters cannot be excluded.
        "~popularity=low",
    ],
)
def test_custom_filter_refuses_bad_values(query):
    with pytest.raises(ParseError):
        run(Article, query, [PopularityFilter])


@pytest.mark.django_db
def test_django_simple_list_filter_runs_unchanged(articles):
    assert titles(run(Article, "range=small", [DjangoDecadeFilter])) == {
        "First",
        "Second",
    }

    with pytest.raises(ParseError):
        run(Article, "range=huge", [DjangoDecadeFilter])


@pytest.mark.django_db
def test_a_custom_filter_without_a_value_does_nothing(articles):
    assert titles(run(Article, "popularity=", [PopularityFilter])) == {
        "First",
        "Second",
        "Third",
    }


# What the admin gets


def test_serialized_filters():
    studio = StubStudio(
        Article,
        ["status", "author__username", "categories", PopularityFilter, SizeFilter],
    )

    serialized = serialize_list_filters(studio, None)

    assert [entry["name"] for entry in serialized] == [
        "status",
        "author__username",
        "categories",
        "popularity",
        "size",
    ]
    assert serialized[0]["field"]["choices"]
    assert serialized[1]["label"] == "Author username"
    assert serialized[1]["field"]["type"] == "CharField"
    assert serialized[2]["field"]["related_model"] == "testapp.category"
    assert serialized[3] == {
        "name": "popularity",
        "label": "Popularity",
        "custom": True,
        "multiple": False,
    }
    assert serialized[4]["multiple"] is True


def test_unusable_entries_are_not_serialized():
    studio = StubStudio(Article, ["titel", "author__password", object, 5])

    assert serialize_list_filters(studio, None) == []


# The endpoints


def superuser_client():
    user = User.objects.create_superuser(username="admin", password="x")
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {create_access_token(user)}")
    return client


@pytest.mark.django_db
def test_filter_options_endpoint(monkeypatch):
    monkeypatch.setattr(
        admin_site._registry[Article], "list_filter", ["status", SizeFilter]
    )
    client = superuser_client()

    response = client.get("/api/content/testapp.article/filters/size/options")
    missing = client.get("/api/content/testapp.article/filters/status/options")

    assert response.status_code == 200, response.content
    assert response.data == [
        {"value": "10", "label": "Ten"},
        {"value": "200", "label": "Two hundred"},
        {"value": "3000", "label": "Three thousand"},
    ]
    assert missing.status_code == 404


@pytest.mark.django_db
def test_list_endpoint_runs_custom_and_relation_filters(monkeypatch, articles):
    monkeypatch.setattr(
        admin_site._registry[Article],
        "list_filter",
        ["author__username", PopularityFilter],
    )
    client = superuser_client()

    response = client.get(
        "/api/content/testapp.article?popularity=high&author__username=bob"
    )
    refused = client.get("/api/content/testapp.article?author__email=a@x.nl")

    assert response.status_code == 200, response.content
    assert [item["title"] for item in response.data["results"]] == ["Second"]
    assert refused.status_code == 400


@pytest.mark.django_db
def test_relation_options_for_a_declared_path(monkeypatch):
    from django.contrib.auth.models import Group

    group = Group.objects.create(name="Editors")
    monkeypatch.setattr(
        admin_site._registry[Article], "list_filter", ["author__groups"]
    )
    client = superuser_client()

    response = client.post(
        "/api/content/testapp.article/relations/author__groups",
        {},
        format="json",
    )
    undeclared = client.post(
        "/api/content/testapp.article/relations/author__user_permissions",
        {},
        format="json",
    )

    assert response.status_code == 200, response.content
    assert [item["id"] for item in response.data] == [str(group.pk)]
    assert undeclared.status_code == 400


# System checks


def checks_for(studio_class, model=Article):
    original = admin_site._registry.pop(model)
    admin_site._registry[model] = studio_class(model, admin_site)

    try:
        return check_content_studio()
    finally:
        admin_site._registry[model] = original


def test_custom_filters_and_paths_pass_the_checks():
    class Fine(ModelStudio):
        list_filter = [
            "status",
            "author__username",
            "review__stars",
            PopularityFilter,
            DjangoDecadeFilter,
        ]

    messages = checks_for(Fine)

    assert not [
        m
        for m in messages
        if m.id
        in (
            "content_studio.E011",
            "content_studio.E042",
            "content_studio.E043",
            "content_studio.W005",
        )
    ]


def test_paths_through_protected_fields_fail_the_checks():
    class Probing(ModelStudio):
        exclude = ["body"]
        list_filter = ["author__password", "body", "title__foo"]

    errors = [m for m in checks_for(Probing) if m.id == "content_studio.E042"]

    assert len(errors) == 3
    assert "password" in str(errors[0])


def test_broken_custom_filters_fail_the_checks():
    class NoTitle(ListFilter):
        parameter_name = "x"

        def queryset(self, request, queryset, value):
            return queryset

    class NoQueryset(ListFilter):
        title = "Y"
        parameter_name = "y"

    class Clash(PopularityFilter):
        parameter_name = "status"

    class Reserved(PopularityFilter):
        parameter_name = "search"

    class Broken(ModelStudio):
        list_filter = ["status", NoTitle, NoQueryset, Clash, Reserved]

    errors = [m for m in checks_for(Broken) if m.id == "content_studio.E043"]

    assert len(errors) == 4


def test_ignored_entries_warn():
    class Mixed(ModelStudio):
        list_filter = [
            ("status", django_admin.ChoicesFieldListFilter),
            django_admin.BooleanFieldListFilter,
        ]

    warnings = [m for m in checks_for(Mixed) if m.id == "content_studio.W005"]

    assert len(warnings) == 2
    assert "default filter" in str(warnings[0])
    assert "ignored" in str(warnings[1])


# Text fields without choices


def test_every_filter_says_its_control():
    studio = StubStudio(
        Article,
        [
            "status",
            "published_at",
            "views",
            "author",
            "categories",
            "review",
            "title",
            "body",
            "author__username",
        ],
    )

    controls = {
        entry["name"]: entry["control"] for entry in serialize_list_filters(studio, None)
    }

    assert controls == {
        "status": "choices",
        "published_at": "date",
        "views": "number",
        "author": "relation",
        "categories": "many",
        "review": "many",
        "title": "distinct",
        "body": "distinct",
        "author__username": "distinct",
    }


def test_fields_without_a_control_are_left_out():
    from tests.testapp.models import Product

    studio = StubStudio(Product, ["title", "details", "manual"])

    assert [e["name"] for e in serialize_list_filters(studio, None)] == ["title"]


@pytest.mark.django_db
def test_text_filter_values_endpoint(monkeypatch, articles):
    Article.objects.create(title="Fourth, with a comma")
    Article.objects.create(title="")
    monkeypatch.setattr(
        admin_site._registry[Article],
        "list_filter",
        ["status", "title", "author__username"],
    )
    client = superuser_client()

    response = client.get("/api/content/testapp.article/filters/title/values")
    searched = client.get(
        "/api/content/testapp.article/filters/title/values?search=IR"
    )
    across = client.get(
        "/api/content/testapp.article/filters/author__username/values"
    )
    choices = client.get("/api/content/testapp.article/filters/status/values")
    undeclared = client.get("/api/content/testapp.article/filters/body/values")

    assert response.status_code == 200, response.content
    # Distinct, sorted, without empty values.
    assert response.data == {
        "values": ["First", "Fourth, with a comma", "Second", "Third"],
        "more": False,
    }
    assert searched.data["values"] == ["First", "Third"]
    assert across.data["values"] == ["ann", "bob"]
    assert choices.status_code == 404
    assert undeclared.status_code == 404


@pytest.mark.django_db
def test_text_filter_values_are_capped(monkeypatch):
    from content_studio import filters

    monkeypatch.setattr(filters, "DISTINCT_VALUES_LIMIT", 2)
    for title in ["A", "B", "C"]:
        Article.objects.create(title=title)

    result = filters.get_distinct_values(Article.objects.all(), "title")

    assert result == {"values": ["A", "B"], "more": True}


@pytest.mark.django_db
def test_text_filter_values_leave_out_what_the_list_leaves_out(monkeypatch):
    Article.objects.create(title="Visible")
    Article.objects.create(title="Hidden")
    studio = admin_site._registry[Article]
    monkeypatch.setattr(studio, "list_filter", ["title"])
    # On the class: an instance attribute would outlive the test.
    monkeypatch.setattr(
        type(studio),
        "get_queryset",
        lambda self, request: Article.objects.exclude(title="Hidden"),
    )
    client = superuser_client()

    response = client.get("/api/content/testapp.article/filters/title/values")

    assert response.status_code == 200, response.content
    assert response.data["values"] == ["Visible"]


@pytest.mark.django_db
def test_text_filter_matches_any_picked_value(articles):
    Article.objects.create(title="Fourth, with a comma")

    result = run(Article, r"title=First,Fourth\, with a comma", ["title"])

    assert titles(result) == {"First", "Fourth, with a comma"}


@pytest.mark.django_db
def test_escaped_commas_reach_custom_filters(articles):
    class CommaFilter(ListFilter):
        title = "Comma"
        parameter_name = "comma"
        options = [("a,b", "A and B"), ("c", "C")]
        multiple = True

        def queryset(self, request, queryset, value):
            assert value == ["a,b", "c"]
            return queryset.filter(title="First")

    result = run(Article, r"comma=a\,b,c", [CommaFilter])

    assert titles(result) == {"First"}


def test_fields_the_list_cannot_filter_on_warn():
    from tests.testapp.models import Product

    class Unfilterable(ModelStudio):
        list_filter = ["title", "details", ("manual", django_admin.FieldListFilter)]

    warnings = [
        m for m in checks_for(Unfilterable, Product) if m.id == "content_studio.W034"
    ]

    assert len(warnings) == 2
    assert "'details', a JSONField" in str(warnings[0])
    assert "'manual', a FileField" in str(warnings[1])
