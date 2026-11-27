from django.urls import include, path

urlpatterns = [
    path("forms/captcha/", include("content_studio.contrib.captcha.urls")),
]
