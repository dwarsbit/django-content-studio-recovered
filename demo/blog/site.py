"""The demo's tiny public site: one article page (MOCKUP SPIKE)."""

from django.http import Http404
from django.shortcuts import render

from content_studio.previews import previewable
from content_studio.publishing import live

from .models import Article


def article_detail(request, slug):
    articles = previewable(request, Article.objects.all(), "published_at")
    article = articles.filter(slug=slug).first() or (
        articles.filter(pk=slug).first() if slug.isdigit() else None
    )

    if article is None:
        raise Http404()

    preview = getattr(request, "content_studio_preview", None)
    is_live = live(Article.objects.filter(pk=article.pk), "published_at").exists()
    response = render(
        request,
        "blog/article.html",
        {
            "article": article,
            "preview": preview if preview and not is_live else None,
            "admin_url": f"/admin/content/demo_blog.article/{article.pk}",
        },
    )

    if preview:
        response["Cache-Control"] = "private, no-store"
        response["X-Robots-Tag"] = "noindex"
        response["Referrer-Policy"] = "no-referrer"

    return response
