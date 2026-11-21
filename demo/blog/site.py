"""
The demo's tiny public site: an article's page. Drafts show with a
preview link (see content_studio.previews), live articles to everyone.
"""

from django.shortcuts import get_object_or_404, render

from content_studio.previews import previewable

from .models import Article


def article_detail(request, slug):
    articles = previewable(request, Article.objects.all())
    lookup = {"pk": int(slug)} if slug.isdigit() else {"slug": slug}
    article = get_object_or_404(articles, **lookup)

    return render(request, "blog/article.html", {"article": article})
