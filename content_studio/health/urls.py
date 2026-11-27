"""
The health endpoints, included at the site's root (their paths are
fixed, since healthchecks hardcode them):

    urlpatterns = [
        path("", include("content_studio.health.urls")),
        path("admin/", include("content_studio.urls")),
    ]
"""

from django.urls import path

from . import views

urlpatterns = [
    path("healthz", views.healthz, name="content_studio_healthz"),
    path("readyz", views.readyz, name="content_studio_readyz"),
    path("statusz", views.statusz, name="content_studio_statusz"),
]
