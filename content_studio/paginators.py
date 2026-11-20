import json
import logging
import math
import time

from django.core.paginator import Paginator
from django.db import DatabaseError, connections, transaction
from django.utils.functional import cached_property
from rest_framework.exceptions import NotFound
from rest_framework.pagination import PageNumberPagination
from rest_framework.response import Response

from . import devtools

# Query parameters that page or sort the list without narrowing it; any
# other parameter is a search or a filter.
NON_FILTER_PARAMS = {"page", "limit", "ordering"}

# An exact count of an unfiltered list that takes longer than this is
# worth replacing with list_count = "estimated".
SLOW_COUNT_SECONDS = 0.5

logger = logging.getLogger(__name__)

# The studios whose slow count was logged: once per studio and process.
_warned_studios: set[str] = set()


class TimedPaginator(Paginator):
    """Django's paginator, timing its COUNT(*)."""

    count_seconds = 0.0

    @cached_property
    def count(self):
        start = time.perf_counter()
        count = super().count
        self.count_seconds = time.perf_counter() - start

        return count


def estimate_count(queryset) -> int | None:
    """
    The database's estimate of the number of rows of the queryset: the
    planner's row estimate on PostgreSQL, None on other databases or
    when the estimate cannot be read. The estimate is of the queryset
    itself, so tenant scoping, soft delete and a studio's get_queryset
    are taken into account.
    """
    if connections[queryset.db].vendor != "postgresql":
        return None

    try:
        # A savepoint: a failed EXPLAIN must not break a request that
        # runs in a transaction (ATOMIC_REQUESTS).
        with transaction.atomic(using=queryset.db):
            plan = json.loads(queryset.order_by().explain(format="json"))
    except (DatabaseError, ValueError):
        return None

    try:
        return int(plan[0]["Plan"]["Plan Rows"])
    except (IndexError, KeyError, TypeError, ValueError):
        return None


class ContentPagination(PageNumberPagination):
    page_size = 20
    page_size_query_param = "limit"
    max_page_size = 100

    # The studio's list_count: "exact", "estimated" or "none".
    count_mode = "exact"

    # Below this estimate an exact count is cheap and runs anyway.
    estimate_threshold = 100_000

    django_paginator_class = TimedPaginator

    # The studio's class name, for the slow count hint.
    studio_name = ""

    def get_count_mode(self, request, view) -> str:
        # The trash and searched or filtered lists count exactly in
        # "estimated" mode: an estimate of a filtered query can be far
        # off, and their counts are what people check.
        if getattr(view, "action", None) == "trash":
            return "exact"

        if self.count_mode == "estimated" and self.is_filtered(request):
            return "exact"

        return self.count_mode

    def is_filtered(self, request) -> bool:
        return any(
            value
            for key, value in request.query_params.items()
            if key not in NON_FILTER_PARAMS
        )

    def paginate_queryset(self, queryset, request, view=None):
        self.count = None
        self.approximate = False
        mode = self.get_count_mode(request, view)
        estimate = None

        if mode == "estimated":
            estimate = estimate_count(queryset)

            if estimate is None or estimate < self.estimate_threshold:
                mode = "exact"

        if mode == "exact":
            page = super().paginate_queryset(queryset, request, view)
            self.count = self.page.paginator.count
            self.current = self.page.number
            self.pages = self.page.paginator.num_pages
            self.has_next = self.page.has_next()
            self.check_slow_count(request, view)

            return page

        return self.paginate_without_count(queryset, request, estimate)

    def check_slow_count(self, request, view):
        """
        A slow exact count of an unfiltered list, on a studio that counts
        exactly: logged as a warning once per studio and process, and
        shown in the developer tools while they are on, suggesting
        list_count = "estimated". Filtered lists and the trash are counted
        exactly whatever list_count is, so they get no hint.
        """
        seconds = self.page.paginator.count_seconds

        if (
            seconds < SLOW_COUNT_SECONDS
            or self.count_mode != "exact"
            or not self.studio_name
            or getattr(view, "action", None) == "trash"
            or self.is_filtered(request)
        ):
            return

        message = (
            f"Counting the list of {self.studio_name} took {seconds:.1f} "
            f'seconds. Set list_count = "estimated" on {self.studio_name} '
            'to show an estimate on large tables, or "none" to skip the count.'
        )

        if self.studio_name not in _warned_studios:
            _warned_studios.add(self.studio_name)
            # The developer tools count every slow count (below), so the
            # log record stays out of them.
            logger.warning(message, extra={"devtools": False})

        devtools.report(
            "warning",
            message,
            code="slow_count",
            title=f"Slow count on {self.studio_name}",
            snippet=(
                f"class {self.studio_name}(ModelStudio):\n"
                '    list_count = "estimated"'
            ),
            docs=f"{devtools.DOCS_URL}/list-page#large-tables",
            studio=self.studio_name,
            key=f"slow_count:{self.studio_name}",
            source="server",
            request=request,
        )

    def paginate_without_count(self, queryset, request, estimate):
        """
        A page without COUNT(*): one row more than the page holds tells
        whether there is a next page. The last page knows the exact
        total; other pages report the estimate, if any.
        """
        page_size = self.get_page_size(request)

        if not page_size:
            return None

        try:
            number = int(request.query_params.get(self.page_query_param, 1))
        except (TypeError, ValueError):
            number = 1

        if number < 1:
            raise NotFound("Invalid page.")

        offset = (number - 1) * page_size
        rows = list(queryset[offset : offset + page_size + 1])

        if not rows and number > 1:
            raise NotFound("Invalid page.")

        self.request = request
        self.current = number
        self.has_next = len(rows) > page_size
        rows = rows[:page_size]

        if not self.has_next:
            self.count = offset + len(rows)
            self.pages = max(number, 1)
        elif estimate is not None:
            # The estimate is at least the rows seen so far.
            self.count = max(estimate, offset + page_size + 1)
            self.approximate = True
            self.pages = math.ceil(self.count / page_size)
        else:
            self.pages = None

        return rows

    def get_paginated_response(self, data):
        return Response(
            {
                "pagination": {
                    # None when the list is not counted; an estimate
                    # when approximate.
                    "count": self.count,
                    "approximate": self.approximate,
                    "current": self.current,
                    "pages": self.pages,
                    "has_next": self.has_next,
                },
                "results": data,
            }
        )
