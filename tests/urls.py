"""
The test project's URLs: the admin at the root, as before, and the
captcha's endpoints at /api/cap/ (content_studio.W043 otherwise).
"""

from django.urls import include, path

urlpatterns = [
    path("api/cap/", include("content_studio.contrib.captcha.urls")),
    path("", include("content_studio.urls")),
]
