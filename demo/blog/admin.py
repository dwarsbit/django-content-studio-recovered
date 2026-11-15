"""
Content Studio registration for the demo project — the documented pattern:
`@register` the model, customize through `ModelStudio` options on the site
configured in CONTENT_STUDIO (demo.blog.studio.admin_site).
"""

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import Q
from django.db.models.functions import Now

from content_studio import register, user_studios, widgets
from content_studio.admin import ModelStudio, RelationDisplay, InlineModelStudio
from content_studio.analytics import Analytics
from content_studio.form import (
    ActivityLog,
    Callout,
    Condition,
    Field,
    FormSet,
    SEOPreview,
    Subtitle,
    Text,
)
from content_studio.actions import bulk_action
from content_studio.filters import ListFilter

from . import models


class ReviewInline(InlineModelStudio):
    model = models.Review
    # Reviews are dragged into order per article.
    reorder_field = "position"


@register(get_user_model())
class UserStudio(user_studios.UserStudio):
    # The built-in user studio's layout: account details and permissions
    # on tabs, the status, dates and activity in the sidebar.
    table_display = ["username", "first_name", "last_name", "email", "is_superuser"]
    search_fields = ["username", "first_name", "last_name", "email"]

    def get_relation_display(self, obj, request):
        # Authors and actors show by name, falling back to the username.
        return RelationDisplay(
            title=obj.get_full_name() or obj.username,
            description=obj.email,
            initials=f"{obj.first_name[:1]}{obj.last_name[:1]}" or obj.username[:2],
        )


@register(models.Category)
class CategoryStudio(ModelStudio):
    icon = "ph-bold ph-tag"
    table_display = ["name", "color", "description"]
    search_fields = ["name"]
    edit_main = ["name", "description", "color"]
    # Categories are dragged into order; the list follows it.
    reorder_field = "position"

    def get_relation_display(self, obj, request):
        return RelationDisplay(
            title=obj.name,
            description=f"{obj.article_set.count()} article(s)",
            icon="ph-bold ph-tag",
        )


@register(models.MediaItem)
class MediaItemStudio(ModelStudio):
    icon = "ph-bold ph-image"
    table_display = ["name", "type", "folder"]

    def get_relation_display(self, obj, request):
        return RelationDisplay(
            title=obj.name,
            initials=obj.name[:2],
            # Image items show their own picture as the avatar.
            avatar=obj.file.url if obj.type == "image" and obj.file else None,
        )


@register(models.MediaFolder)
class MediaFolderStudio(ModelStudio):
    icon = "ph-bold ph-folder"
    table_display = ["name"]


class ReadingTime(Callout):
    title = "Reading time"

    def get_text(self, obj, request):
        minutes = max(1, len(obj.body.split()) // 200)
        return f"About **{minutes} min** to read."


class MeetsHouseStyle(Condition):
    """The demo's house style for search descriptions: a full sentence,
    without shouting or "click here"."""

    fields = ["meta_description"]

    def check(self, values, request):
        text = (values["meta_description"] or "").strip()

        return (
            text.endswith(".")
            and not text.isupper()
            and "click here" not in text.lower()
        )


class ReachFilter(ListFilter):
    """A custom list filter: buckets of views, several at once."""

    title = "Reach"
    parameter_name = "reach"
    multiple = True
    options = [
        ("niche", "Niche (under 100 views)"),
        ("steady", "Steady (100 to 999)"),
        ("hit", "Hit (1,000 or more)"),
    ]

    BUCKETS = {
        "niche": Q(views__lt=100),
        "steady": Q(views__gte=100, views__lt=1000),
        "hit": Q(views__gte=1000),
    }

    def queryset(self, request, queryset, value):
        condition = Q()
        for bucket in value:
            condition |= self.BUCKETS[bucket]
        return queryset.filter(condition)


@register(models.Article)
class ArticleStudio(ModelStudio):
    icon = "ph-bold ph-article"
    table_display = ["title", "status", "featured", "views", "author", "published_at"]
    # The list view's rows; both views are offered, with a toggle.
    list_views = ["table", "list"]
    list_item_display = {
        "title": "title",
        "description": "body",
        "meta": "get_status_display",
        "thumbnail": "cover",
    }
    # Newest first, so the seeded demo article leads the list.
    ordering = ["-pk"]
    # One field per filter type: choices (status), boolean (featured),
    # number range (views), date range (published_at), foreign key
    # (author) and many to many (categories); a path across a reverse
    # relation (review__stars) and a custom filter (ReachFilter).
    list_filter = [
        "status",
        "featured",
        "views",
        "published_at",
        "author",
        "categories",
        "review__stars",
        ReachFilter,
    ]
    # Opt-in soft delete: deleting moves articles to the trash, where
    # they can be restored or permanently deleted.
    soft_delete = "removed_at"
    # Export the table, and import articles from a file: rows with an id
    # update that article, others create one. Authors are given by
    # username and categories by name.
    allow_export = True
    import_fields = [
        "title",
        "slug",
        "body",
        "meta_description",
        "status",
        "author",
        "categories",
        "featured",
        "views",
        "published_at",
    ]
    import_lookups = {"author": "username", "categories": "name"}
    # Each row's menu: publish or assign that one article, duplicate it,
    # or move it to the trash.
    row_actions = ["publish", "assign", "duplicate", "delete"]
    # The edit page's more actions menu offers these on the article.
    edit_actions = ["assign", "set_status"]
    allow_duplication = True
    search_fields = ["title"]
    inlines = [ReviewInline]
    # The slug follows the title while an article is created.
    prepopulated_fields = {"slug": ["title"]}
    edit_main = [
        FormSet(
            title="Content",
            description="The article itself",
            fields=[
                Field("cover", widget=widgets.CoverImageWidget),
                "title",
                Text("Write for the web: short paragraphs, **one idea** each."),
                "body",
                Field("video_url", widget=widgets.EmbedWidget),
                Subtitle("Publishing"),
                "status",
                "categories",
            ],
        ),
        FormSet(
            title="Search",
            description="How the article shows up in search results",
            fields=[
                "slug",
                Field(
                    "meta_description",
                    widget=widgets.InputWidget(recommended_length=160),
                ),
                # Shown while the description breaks the house style;
                # the check runs on the server.
                Callout(
                    "Write the description as one full sentence, ending in "
                    'a period, without capitals throughout or "click here".',
                    title="House style",
                    variant="warning",
                    when=~Q(meta_description="") & ~MeetsHouseStyle(),
                ),
                SEOPreview(
                    title_field="title",
                    description_field="meta_description",
                    base_url="https://example.com/blog/",
                    path_field="slug",
                    site_name="Demo site",
                ),
            ],
        ),
    ]
    edit_sidebar = [
        ReadingTime(),
        # The publication date only matters once the article is published.
        Field("published_at", when=Q(status="published")),
        Callout(
            "Scheduled: the article goes live at its publication date.",
            variant="info",
            when=Q(status="published", published_at__gt=Now()),
        ),
        "author",
        "featured",
        "views",
        # The demo site serves articles at /articles/<id>/.
        Analytics(path_field="pk", path_prefix="/articles/", path_suffix="/"),
        ActivityLog(),
    ]

    @bulk_action(
        label="Publish",
        icon="ph-bold ph-paper-plane-tilt",
        confirm="...",
        allowed_permissions=["change"],
        destructive=False,
    )
    def publish(self, request, queryset):
        queryset.update(status=models.Article.Status.PUBLISHED)
        return f"Published {queryset.count()} articles."

    # An action with an input form: the dialog asks for an author (a
    # model field, with the edit form's picker) and an optional note,
    # and offers to email the author once a note is written.
    @bulk_action(
        label="Assign",
        icon="ph-bold ph-user-switch",
        fields=[
            "author",
            Field(
                "note",
                form_field=forms.CharField(
                    label="Note for the author",
                    required=False,
                    widget=forms.Textarea,
                ),
            ),
            Field(
                "notify",
                form_field=forms.BooleanField(
                    label="Email the note to the author", required=False
                ),
                when=~Q(note=""),
            ),
        ],
    )
    def assign(self, request, queryset, data):
        count = queryset.update(author=data["author"])
        return f"Assigned {count} articles to {data['author'] or 'nobody'}."

    @bulk_action(
        label="Set status",
        icon="ph-bold ph-flag",
        fields=["status", Field("published_at", when=Q(status="published"))],
    )
    def set_status(self, request, queryset, data):
        values = {"status": data["status"]}
        if "published_at" in data:
            values["published_at"] = data["published_at"]
        count = queryset.update(**values)
        return f"Updated {count} articles."


@register(models.SiteSettings)
class SiteSettingsStudio(ModelStudio):
    icon = "ph-bold ph-sliders-horizontal"
    is_singleton = True
    edit_main = [
        "site_name",
        "tagline",
        "contact_email",
        Subtitle("Brand"),
        Text("The colors the site's header, links and buttons use."),
        "brand_color",
        "accent_color",
        Subtitle("Integrations"),
        Field("social_links", widget=widgets.KeyValueWidget),
        Field("head_code", widget=widgets.CodeWidget(language="html")),
        Subtitle("Office"),
        Field(
            "office_location",
            widget=widgets.MapWidget(center=(52.37, 4.9), zoom=11),
        ),
    ]


@register(models.LandingPage)
class LandingPageStudio(ModelStudio):
    icon = "ph-bold ph-browser"
    table_display = ["title"]
    edit_main = ["title", "body", "sections"]
