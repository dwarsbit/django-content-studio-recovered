"""
The list page's count (ModelStudio.list_count): an exact COUNT(*), the
database's estimate for large tables, or no count at all.
"""

from types import SimpleNamespace
from unittest import mock

import pytest
from django.contrib.auth import models as auth_models
from django.db import connection
from django.test.utils import CaptureQueriesContext
from rest_framework.exceptions import NotFound
from rest_framework.request import Request
from rest_framework.test import APIRequestFactory

from content_studio.admin import ModelStudio
from content_studio.checks import list_config_errors
from content_studio import paginators
from content_studio.paginators import ContentPagination, estimate_count
from tests.testapp.models import Article


def paginate(mode, params=None, action="list", page_size=5, studio="ArticleStudio"):
    class Pagination(ContentPagination):
        count_mode = mode
        studio_name = studio

    Pagination.page_size = page_size
    paginator = Pagination()
    request = Request(APIRequestFactory().get("/", params or {}))
    view = SimpleNamespace(action=action)

    with CaptureQueriesContext(connection) as queries:
        rows = paginator.paginate_queryset(
            Article.objects.order_by("pk"), request, view
        )

    pagination = paginator.get_paginated_response([]).data["pagination"]

    return rows, pagination, [query["sql"] for query in queries]


def counted(queries):
    return any("COUNT(" in sql.upper() for sql in queries)


@pytest.fixture
def articles(db):
    author = auth_models.User.objects.create(username="writer")
    Article.objects.bulk_create(
        Article(title=f"Article {i}", author=author) for i in range(12)
    )


def test_exact_counts_every_list(articles):
    rows, pagination, queries = paginate("exact")

    assert len(rows) == 5
    assert pagination == {
        "count": 12,
        "approximate": False,
        "current": 1,
        "pages": 3,
        "has_next": True,
        "slow_count": None,
    }
    assert counted(queries)


def test_none_pages_without_counting(articles):
    rows, pagination, queries = paginate("none")

    assert len(rows) == 5
    assert pagination == {
        "count": None,
        "approximate": False,
        "current": 1,
        "pages": None,
        "has_next": True,
        "slow_count": None,
    }
    assert not counted(queries)


def test_none_knows_the_total_on_the_last_page(articles):
    rows, pagination, queries = paginate("none", {"page": 3})

    assert len(rows) == 2
    assert pagination["count"] == 12
    assert pagination["pages"] == 3
    assert pagination["has_next"] is False
    assert not counted(queries)


def test_none_raises_not_found_past_the_end(articles):
    with pytest.raises(NotFound):
        paginate("none", {"page": 4})


def test_estimated_falls_back_to_an_exact_count_without_an_estimate(articles):
    # SQLite has no estimate.
    _, pagination, queries = paginate("estimated")

    assert pagination["count"] == 12
    assert pagination["approximate"] is False
    assert counted(queries)


def test_estimated_counts_exactly_below_the_threshold(articles):
    with mock.patch("content_studio.paginators.estimate_count", return_value=500):
        _, pagination, queries = paginate("estimated")

    assert pagination["count"] == 12
    assert pagination["approximate"] is False
    assert counted(queries)


def test_estimated_reports_the_estimate_for_large_tables(articles):
    with mock.patch("content_studio.paginators.estimate_count", return_value=2_300_000):
        rows, pagination, queries = paginate("estimated")

    assert len(rows) == 5
    assert pagination == {
        "count": 2_300_000,
        "approximate": True,
        "current": 1,
        "pages": 460_000,
        "has_next": True,
        "slow_count": None,
    }
    assert not counted(queries)


def test_estimated_is_exact_on_the_last_page(articles):
    with mock.patch("content_studio.paginators.estimate_count", return_value=2_300_000):
        _, pagination, _ = paginate("estimated", {"page": 3})

    assert pagination["count"] == 12
    assert pagination["approximate"] is False
    assert pagination["has_next"] is False


@pytest.mark.parametrize("params", [{"search": "Article"}, {"author": "1"}])
def test_estimated_counts_searches_and_filters_exactly(articles, params):
    with mock.patch(
        "content_studio.paginators.estimate_count", return_value=2_300_000
    ) as estimate:
        _, pagination, queries = paginate("estimated", params)

    estimate.assert_not_called()
    assert pagination["approximate"] is False
    assert counted(queries)


def test_ordering_is_not_a_filter(articles):
    with mock.patch("content_studio.paginators.estimate_count", return_value=2_300_000):
        _, pagination, _ = paginate("estimated", {"ordering": "-title"})

    assert pagination["approximate"] is True


def test_the_trash_counts_exactly(articles):
    _, pagination, queries = paginate("none", action="trash")

    assert pagination["count"] == 12
    assert counted(queries)


def test_estimate_count_is_none_on_other_databases(db):
    assert estimate_count(Article.objects.all()) is None


def test_estimate_count_reads_the_postgres_plan(db):
    plan = '[{"Plan": {"Node Type": "Seq Scan", "Plan Rows": 2300412}}]'
    queryset = Article.objects.all()

    with (
        mock.patch.object(connection, "vendor", "postgresql"),
        mock.patch.object(type(queryset), "explain", return_value=plan),
    ):
        assert estimate_count(queryset) == 2_300_412


def test_unknown_list_count_is_an_error():
    class Studio(ModelStudio):
        list_count = "fast"

    errors = list_config_errors(Studio(Article, None))

    assert [check_id for check_id, _ in errors] == ["content_studio.E046"]


def test_the_studio_sets_the_list_pagination_mode():
    from django.apps import apps

    from content_studio.admin import admin_site

    class Studio(ModelStudio):
        list_count = "none"

    with mock.patch("content_studio.router.content_studio_router.register") as reg:
        apps.get_app_config("content_studio")._create_view_set(
            Article, Studio(Article, admin_site)
        )

    viewset = reg.call_args.args[1]
    assert viewset.pagination_class.count_mode == "none"


@pytest.fixture
def slow_counts(monkeypatch):
    # Every count is slow, and no studio was warned about yet.
    monkeypatch.setattr(paginators, "SLOW_COUNT_SECONDS", 0)
    monkeypatch.setattr(paginators, "_warned_studios", set())


def test_a_slow_count_is_logged_once_per_studio(articles, slow_counts, caplog):
    with caplog.at_level("WARNING", logger="content_studio.paginators"):
        paginate("exact")
        paginate("exact")

    assert len(caplog.records) == 1
    assert 'list_count = "estimated" on ArticleStudio' in caplog.messages[0]


def test_a_slow_count_is_returned_while_debug_is_on(articles, slow_counts, settings):
    settings.DEBUG = True

    _, pagination, _ = paginate("exact")

    assert pagination["slow_count"]["studio"] == "ArticleStudio"
    assert pagination["slow_count"]["seconds"] >= 0


def test_a_slow_count_is_not_returned_without_debug(articles, slow_counts, settings):
    settings.DEBUG = False

    _, pagination, _ = paginate("exact")

    assert pagination["slow_count"] is None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"params": {"search": "Article"}},
        {"action": "trash"},
        {"studio": ""},
    ],
)
def test_no_slow_count_hint_where_list_count_cannot_help(
    articles, slow_counts, settings, caplog, kwargs
):
    settings.DEBUG = True

    with caplog.at_level("WARNING", logger="content_studio.paginators"):
        _, pagination, _ = paginate("exact", **kwargs)

    assert pagination["slow_count"] is None
    assert not caplog.records


def test_a_fast_count_has_no_hint(articles, settings, caplog):
    settings.DEBUG = True

    with caplog.at_level("WARNING", logger="content_studio.paginators"):
        _, pagination, _ = paginate("exact")

    assert pagination["slow_count"] is None
    assert not caplog.records


def test_inlines_and_the_studio_name(db):
    from django.apps import apps

    from content_studio.admin import admin_site

    class ArticleStudio(ModelStudio):
        pass

    with mock.patch("content_studio.router.content_studio_router.register") as reg:
        apps.get_app_config("content_studio")._create_view_set(
            Article, ArticleStudio(Article, admin_site)
        )

    assert reg.call_args.args[1].pagination_class.studio_name == "ArticleStudio"
