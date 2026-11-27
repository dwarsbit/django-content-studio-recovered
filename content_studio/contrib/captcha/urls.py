"""
The captcha's endpoints, included outside the admin at a path of your
choice (the widget finds them by name):

    urlpatterns = [
        path("api/cap/", include("content_studio.contrib.captcha.urls")),
        path("admin/", include("content_studio.urls")),
    ]
"""

from django.urls import path

from . import views

urlpatterns = [
    path(
        "challenge",
        views.ChallengeView.as_view(),
        name="content_studio_captcha_challenge",
    ),
    path("redeem", views.RedeemView.as_view(), name="content_studio_captcha_redeem"),
    path("solver.wasm", views.solver, name="content_studio_captcha_solver"),
]
