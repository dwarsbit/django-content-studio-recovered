from django.urls import include, path

urlpatterns = [
    path("", include("content_studio.health.urls")),
    path("admin/", include("content_studio.urls")),
]
