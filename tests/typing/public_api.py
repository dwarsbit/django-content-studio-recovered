"""
Typical project code against the public API, checked by mypy (with
django-stubs) and Pyright in CI: it guards the package's type hints
against false errors in user code. It is never run or collected by
pytest. Add the patterns users write here when the hints change; see
tests/typing/README.md.
"""

import datetime
from typing import Any

from django.db.models import Q
from django.db.models.functions import Now
from django.utils.translation import gettext_lazy as _

from content_studio import register
from content_studio import widgets
from content_studio.actions import bulk_action
from content_studio.admin import (
    ContentStudioSite,
    InlineModelStudio,
    ModelGroup,
    ModelStudio,
)
from content_studio.analytics import Analytics
from content_studio.dashboard import Dashboard, DashboardWidget
from content_studio.dashboard.activity_log import ActivityLogWidget
from content_studio.dashboard.content_list import ContentListWidget
from content_studio.dashboard.statistic import StatisticWidget
from content_studio.extensions import (
    DashboardPage,
    IFramePage,
    MainMenuButton,
    MainMenuLink,
    UserMenuLink,
)
from content_studio.filters import ListFilter
from content_studio.form import (
    ActivityLog,
    Button,
    ButtonLink,
    ButtonResult,
    Callout,
    Condition,
    Field,
    FieldLayout,
    FormSet,
    FormSetGroup,
    SEOPreview,
    Subtitle,
    TableColumn,
    Text,
    Title,
)
from content_studio.formats import DateTimeFormat, NumberFormat
from content_studio.signals import record_change
from tests.testapp.models import Article, Category, Review

# Components and conditions


class MeetsHouseStyle(Condition):
    fields = ["body"]

    def check(self, values: dict[str, Any], request) -> bool:
        return len(values["body"] or "") < 5000


class ViewOnSiteButton(ButtonLink):
    label = "View on site"
    icon = "ph-bold ph-arrow-square-out"
    copy = True
    when = Q(status="published")

    def get_url(self, obj, request):
        return f"/articles/{obj.pk}/"


class PublishButton(Button):
    label = _("Publish")
    icon = "ph-bold ph-paper-plane-tilt"
    confirm = _("Publish this article?")
    allowed_permissions = ["change"]

    def is_visible(self, obj, request):
        return obj.status != Article.Status.PUBLISHED

    def handle(self, obj, request):
        record_change(request, obj, "updated", _("Published."))
        return _("Published.")


class RotateKeyButton(Button):
    label = "Rotate key"
    destructive = True

    def handle(self, obj, request):
        return ButtonResult(message=_("Rotated."), value="secret")


class WordCount(Text):
    def get_text(self, obj, request):
        return _("Short") if len(obj.body) < 100 else "Long"


# Filters


class PopularityFilter(ListFilter):
    title = _("Popularity")
    parameter_name = "popularity"
    options = [("low", "Under 100 views"), ("high", "100 views or more")]

    def queryset(self, request, queryset, value):
        return queryset.filter(views__lt=100 if value == "low" else 0)


# Studios


class ReviewInline(InlineModelStudio):
    model = Review
    table_display = ["text", "stars"]


@register(Article)
class ArticleStudio(ModelStudio):
    icon = "ph-bold ph-article"
    list_description = _("Everything the blog published.")
    table_display = [
        "title",
        TableColumn(field="published_at", header=_("Published")),
        TableColumn(field="views", format=NumberFormat(decimals=0)),
        TableColumn(field="edited_at", format=DateTimeFormat),
    ]
    list_filter = ["status", "author__username", PopularityFilter]
    search_fields = ["title"]
    prepopulated_fields = {"title": ["body"]}
    inlines = [ReviewInline]
    edit_header = [PublishButton()]
    edit_main = [
        FormSetGroup(
            label=_("Content"),
            formsets=[
                FormSet(
                    title=_("Content"),
                    description="The article itself",
                    fields=[
                        Title("Write for the web"),
                        Field("title", label=_("Headline"), widget=widgets.InputWidget),
                        Text(_("Short paragraphs, **one idea** each.")),
                        Field("body", widget=widgets.TextAreaWidget(rows=12)),
                        FieldLayout(["status", Field("views", col_span=2)], columns=3),
                        Subtitle("Publishing"),
                        Field(
                            "published_at",
                            when=Q(status="published"),
                            widget=widgets.DateTimeWidget(min_date=datetime.date.today),
                        ),
                        Callout(
                            "Keep it under 5000 characters.",
                            title=_("House style"),
                            variant="warning",
                            when=~Q(body="") & ~MeetsHouseStyle(),
                        ),
                        Callout(
                            "Scheduled.",
                            when=Q(published_at__gt=Now()) | MeetsHouseStyle(),
                        ),
                        SEOPreview(title_field="title", site_name=_("Blog")),
                        WordCount(),
                    ],
                    when=MeetsHouseStyle() & Q(status="draft"),
                ),
            ],
        ),
    ]
    edit_sidebar = [
        "author",
        Field("views", readonly=True, label=None),
        ViewOnSiteButton(),
        RotateKeyButton(),
        Analytics(path_field="pk", path_prefix="/articles/"),
        ActivityLog(),
    ]

    @bulk_action(label=_("Publish"), confirm="Sure?", allowed_permissions=["change"])
    def publish(self, request, queryset):
        return f"Published {queryset.count()} articles."


@register(Category)
class CategoryStudio(ModelStudio):
    edit_main = ["name"]
    edit_sidebar = [FormSet(title="Meta", fields=["name"])]


# register returns the class itself.
category_studio: type[CategoryStudio] = CategoryStudio


# The site


class PublishedWidget(StatisticWidget):
    name = "published"
    col_span = 2
    refresh_interval = 10

    def get_data(self, request):
        return {"title": _("Published"), "value": 3}


class LatestWidget(ContentListWidget):
    refresh_interval = 2.5

    def get_data(self, request):
        return {"title": "Latest", "content": []}


class CustomWidget(DashboardWidget):
    widget_type = "StatisticWidget"
    name = "custom"
    widget_id = "0b6a0d8c-1f6e-4d5c-9a52-6e1f3c1b2a90"


class ClearCacheButton(MainMenuButton):
    label = "Clear cache"
    icon = "ph-bold ph-broom"
    confirm = _("Clear the cache for every visitor?")

    def handle(self, request):
        return "The cache is cleared."


class BlogStudioSite(ContentStudioSite):
    site_header = "Blog"
    site_title = _("Blog studio")
    index_title = "Dashboard"
    default_widget_mapping = {
        **ContentStudioSite.default_widget_mapping,
        "django.db.models.TextField": widgets.TextAreaWidget(rows=4),
    }
    dashboard = Dashboard(
        widgets=[PublishedWidget(), LatestWidget(), ActivityLogWidget()]
    )
    model_groups = [
        ModelGroup("content", label=_("Content"), models=[Article]),
    ]
    extensions = [
        MainMenuLink(url="https://status.example.com", label=_("Status")),
        UserMenuLink(url="/help/", label="Help", icon="ph-bold ph-question"),
        IFramePage(path="reports/", iframe_url="https://example.com/"),
        DashboardPage(
            path="stats/",
            title=_("Stats"),
            description="How the blog is doing.",
            dashboard=Dashboard(widgets=[CustomWidget()]),
        ),
        ClearCacheButton(),
    ]
    profile_fields = ["first_name", Field("email", label=_("Email"))]


admin_site = BlogStudioSite()
