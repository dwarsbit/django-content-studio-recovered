"""
The showcase seed: replaces the demo's content with a complete, realistic
magazine (see content.py) for screenshots and demos. Run it with
`python demo/manage.py seed_demo --showcase`.
"""

import uuid
from datetime import timedelta

from django.apps import apps
from django.contrib.admin.models import ADDITION, CHANGE, LogEntry
from django.contrib.auth import get_user_model
from django.contrib.contenttypes.models import ContentType
from django.core.files.base import ContentFile
from django.utils import timezone
from django.utils.text import slugify
from django.utils.html import escape

from content_studio.media_library.metadata import read_image_size

from ..models import (
    Article,
    Category,
    LandingPage,
    MediaFolder,
    MediaItem,
    Review,
    SiteSettings,
)
from . import content
from .images import render


def run(stdout, password):
    now = timezone.now()
    clear()
    users = seed_users(password)
    media = seed_media(stdout)
    categories = seed_categories()
    articles = seed_articles(users, media, categories, now)
    seed_reviews(articles)
    seed_landing_page(media, articles)
    SiteSettings.objects.create(**content.SITE)
    seed_activity(users, articles, now)
    if apps.is_installed("content_studio.notifications"):
        seed_notifications(users, articles, now)
    stdout.write(
        f"Showcase ready: {len(articles)} articles, {len(media)} images, "
        f"{len(categories)} categories."
    )


def clear():
    for item in MediaItem.objects.all():
        # Deleting the files too keeps file names stable across reseeds.
        item.file.delete(save=False)
        item.delete()
    for model in (Article, Category, MediaFolder, LandingPage, SiteSettings):
        model._base_manager.all().delete()
    LogEntry.objects.all().delete()
    if apps.is_installed("content_studio.notifications"):
        from content_studio.notifications.models import Notification

        Notification.objects.all().delete()


def seed_users(password):
    user_model = get_user_model()
    users = {}
    for username, (first, last, email, superuser) in content.PEOPLE.items():
        user, created = user_model.objects.get_or_create(username=username)
        user.first_name, user.last_name, user.email = first, last, email
        user.is_staff = True
        user.is_superuser = superuser
        if created:
            user.set_password(password)
        user.save()
        users[username] = user
    return users


def seed_media(stdout):
    media = {}
    for folder_name, items in content.MEDIA.items():
        folder = folder_name and MediaFolder.objects.create(name=folder_name)
        for scene, name, alt, tags, focal_point in items:
            stdout.write(f"Drawing {name}...")
            data = ContentFile(render(scene))
            item = MediaItem(
                name=name,
                type="image",
                alt_text=alt,
                tags=tags,
                folder=folder or None,
                metadata=read_image_size(data),
                properties={"focal_point": focal_point} if focal_point else {},
            )
            item.file.save(f"{scene}.jpg", data, save=False)
            item.save()
            media[scene] = item
    return media


def seed_categories():
    return {
        name: Category.objects.create(
            name=name, color=color, description=description, position=position
        )
        for position, (name, color, description) in enumerate(content.CATEGORIES, 1)
    }


def seed_articles(users, media, categories, now):
    # Drafts first, then the published articles oldest to newest: the
    # list is newest first by pk, so the latest story leads it.
    ordered = sorted(
        content.ARTICLES,
        key=lambda a: (a["days"] is not None, -(a["days"] or 0)),
    )
    articles = {}
    for spec in ordered:
        days = spec["days"]
        published_at = now - timedelta(days=days, hours=3) if days is not None else None
        author = users[spec["author"]]
        body = "\n\n".join(spec["body"])
        article = Article.objects.create(
            title=spec["title"],
            slug=slugify(spec["title"]),
            body=body,
            # The first sentence, as the search-result description.
            meta_description=spec["body"][0].split(". ")[0].rstrip(".") + ".",
            **translated_values(spec["title"]),
            status=(
                Article.Status.PUBLISHED if days is not None else Article.Status.DRAFT
            ),
            author=author,
            cover=media[spec["cover"]],
            featured=spec.get("featured", spec["views"] > 6000),
            views=spec["views"],
            published_at=published_at,
            created_by=author,
            edited_by=users["maya"],
            edited_at=(published_at or now) - timedelta(hours=5),
        )
        article.categories.set([categories[name] for name in spec["categories"]])
        articles[spec["title"]] = article
    return articles


def translated_values(title):
    """The Dutch and German columns of an article, from TRANSLATIONS."""
    values = {}

    for language, fields in content.TRANSLATIONS.get(title, {}).items():
        for name, value in fields.items():
            if isinstance(value, list):
                value = "\n\n".join(value)
            values[f"{name}_{language}"] = value

    return values


def seed_reviews(articles):
    for title, reviews in content.REVIEWS.items():
        for position, (text, stars) in enumerate(reviews, 1):
            Review.objects.create(
                article=articles[title], text=text, stars=stars, position=position
            )


def blocks(specs, media):
    result = []
    for kind, data in specs:
        data = dict(data)
        if kind == "image":
            data["image"] = media[data["image"]].pk
        if kind == "columns":
            data = {side: blocks(data[side], media) for side in ("left", "right")}
        result.append({"id": str(uuid.uuid4()), "type": kind, "data": data})
    return result


def rich_text_extras(media, articles):
    """
    The landing page's rich text after its intro: an image from the
    media library, a link to an article and a table, as the rich text
    editor stores them.
    """
    image = media["misty-forest"]
    article = articles["Five forest walks within an hour of the city"]
    return (
        '<figure class="rich-text-figure align-center">'
        f'<img src="{image.file.url}" alt="{escape(image.alt_text)}" '
        f'data-media-id="{image.pk}" data-size="original">'
        "<figcaption>Morning fog in the pines, an hour from the city.</figcaption>"
        "</figure>"
        "<h3>Where to start</h3>"
        "<p>New here? Begin with "
        f'<a href="{article.get_absolute_url()}" data-link-model="demo_blog.article" '
        f'data-link-id="{article.pk}">five forest walks within an hour of the city</a>, '
        "then pick a route below.</p>"
        "<table><tbody>"
        "<tr><th><p>Route</p></th><th><p>Train</p></th><th><p>Time</p></th></tr>"
        "<tr><td><p>Oslo to Dombås</p></td><td><p>Dovrebanen</p></td><td><p>4 h 10 min</p></td></tr>"
        "<tr><td><p>Dombås to Åndalsnes</p></td><td><p>Raumabanen</p></td><td><p>1 h 20 min</p></td></tr>"
        "<tr><td><p>Trondheim to Bodø</p></td><td><p>Nordlandsbanen</p></td><td><p>9 h 45 min</p></td></tr>"
        "</tbody></table>"
    )


def seed_landing_page(media, articles):
    page = content.LANDING_PAGE
    LandingPage.objects.create(
        title=page["title"],
        body=page["body"] + rich_text_extras(media, articles),
        sections=blocks(page["sections"], media),
    )
    LandingPage.objects.create(title="About Northbound", body=content.SITE["tagline"])


def seed_activity(users, articles, now):
    """The activity log: who created and edited what, recently."""
    article_type = ContentType.objects.get_for_model(Article)
    entries = []
    for index, article in enumerate(
        sorted(articles.values(), key=lambda a: a.pk, reverse=True)
    ):
        entries.append(
            LogEntry(
                user=article.author,
                content_type=article_type,
                object_id=str(article.pk),
                object_repr=str(article)[:200],
                action_flag=CHANGE if index % 3 else ADDITION,
                change_message="[]",
                action_time=now - timedelta(hours=2 + index * 7, minutes=index * 13),
            )
        )
    LogEntry.objects.bulk_create(entries)


def seed_notifications(users, articles, now):
    """Unread notifications for Alex: what the team did lately."""
    from content_studio.notifications.models import Notification

    article_type = ContentType.objects.get_for_model(Article)
    admin = users["admin"]
    notes = [
        (
            "content.updated",
            "maya",
            "Why the best trips start with a slow train",
            3,
            12,
        ),
        ("content.created", "sam", "A weekend guide to the northern lights", 1, 50),
        (
            "content.updated",
            "priya",
            "Colour notes: the palette of a northern autumn",
            2,
            190,
        ),
        (
            "content.created",
            "jonas",
            "After dark: a night walk through the old town",
            1,
            1440,
        ),
    ]
    for event, actor, title, count, minutes in notes:
        article = articles[title]
        notification = Notification.objects.create(
            recipient=admin,
            event=event,
            actor=users[actor],
            content_type=article_type,
            object_id=str(article.pk),
            object_repr=str(article),
            count=count,
            key=f"{article_type.pk}:{article.pk}",
        )
        Notification.objects.filter(pk=notification.pk).update(
            created_at=now - timedelta(minutes=minutes),
            updated_at=now - timedelta(minutes=minutes),
        )
