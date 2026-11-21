from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from demo.blog.site import article_detail

urlpatterns = [
    path("admin/", include("content_studio.urls")),
    # A tiny public site: an article's page, with previews of drafts.
    path("blog/<slug:slug>/", article_detail, name="article"),
]

# serve uploaded media during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
