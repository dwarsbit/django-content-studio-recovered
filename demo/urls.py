from django.conf import settings
from django.conf.urls.static import static
from django.urls import include, path

from demo.blog.site import article_detail, contact

urlpatterns = [
    path("admin/", include("content_studio.urls")),
    # The captcha's endpoints, for the contact form's widget.
    path("api/cap/", include("content_studio.contrib.captcha.urls")),
    # A tiny public site: an article's page, with previews of drafts, and
    # a contact form behind the captcha.
    path("blog/<slug:slug>/", article_detail, name="article"),
    path("contact/", contact, name="contact"),
]

# serve uploaded media during development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
