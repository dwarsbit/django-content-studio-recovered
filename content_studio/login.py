"""
Completing a login. Every way of logging in (the password, a set-password
link) ends in complete_login(): with the two-factor app installed and
two-factor login on for the user, it answers with a challenge for the
code step instead of a session; otherwise it starts the session.

The session itself comes from the token backend. Tokens record whether
the code step was passed, so a session without it is refused for a user
who must use two-factor login (see JsonWebTokenBackend).
"""

import inspect

from django.apps import apps
from django.contrib.auth.signals import user_logged_in
from rest_framework.response import Response

from .settings import cs_settings

TWO_FACTOR_APP = "content_studio.contrib.two_factor"

# The values TWO_FACTOR_REQUIRED takes besides None.
TWO_FACTOR_REQUIRED_VALUES = ("superusers", "all")


def two_factor_installed() -> bool:
    return apps.is_installed(TWO_FACTOR_APP)


def two_factor_required(user) -> bool:
    """Whether TWO_FACTOR_REQUIRED asks two-factor login of the user."""
    required = cs_settings.TWO_FACTOR_REQUIRED

    if not two_factor_installed() or not required:
        return False

    if required == "superusers":
        return bool(getattr(user, "is_superuser", False))

    return required == "all"


def has_two_factor(user) -> bool:
    """Whether the user has set up two-factor login."""
    if not two_factor_installed():
        return False

    from .contrib.two_factor.models import get_authenticator

    return get_authenticator(user) is not None


def needs_two_factor(user) -> bool:
    """Whether a session of the user must have passed the code step."""
    return has_two_factor(user) or two_factor_required(user)


def session_stamp(user) -> str:
    """
    A value that changes when two-factor login is turned on, off or
    reset: the token backend signs it into every token, so those
    changes end the user's other sessions. Empty without two-factor.
    """
    if not two_factor_installed():
        return ""

    from .contrib.two_factor.models import get_authenticator

    authenticator = get_authenticator(user)

    return f"{authenticator.pk}:{authenticator.secret}" if authenticator else ""


def user_queryset():
    """The users the token backend reads, with what session_stamp needs."""
    from django.contrib.auth import get_user_model

    queryset = get_user_model()._default_manager.all()

    if two_factor_installed():
        from .contrib.two_factor.models import AUTHENTICATOR_RELATED_NAME

        queryset = queryset.select_related(AUTHENTICATOR_RELATED_NAME)

    return queryset


def issue_session(user, request, *, two_factor: bool = False):
    """
    The token backend's response that starts a session. two_factor
    records that the code step was passed, for backends that take it.
    """
    backend = cs_settings.ADMIN_SITE.token_backend.active_backend
    method = backend.get_response_for_user

    try:
        parameters = inspect.signature(method).parameters
    except (TypeError, ValueError):
        parameters = {}

    if "two_factor" in parameters or any(
        p.kind is inspect.Parameter.VAR_KEYWORD for p in parameters.values()
    ):
        return method(user, request, two_factor=two_factor)

    return method(user, request)


def finish_login(user, request, *, two_factor: bool = False):
    """
    The user is logged in: Django's user_logged_in signal (last_login,
    audit tools) and the session.
    """
    django_request = getattr(request, "_request", request)
    user_logged_in.send(sender=user.__class__, request=django_request, user=user)

    return issue_session(user, request, two_factor=two_factor)


def complete_login(user, request, *, backend=None):
    """
    The answer to a login whose first factor (the password, a link) is
    right: the session, or the challenge for the code step. A login
    backend whose identity provider did two-factor itself sets
    handles_two_factor = True and skips the code step.
    """
    if getattr(backend, "handles_two_factor", False) or not needs_two_factor(user):
        return finish_login(user, request)

    from .contrib.two_factor.challenges import make_challenge

    return Response(
        {
            "two_factor": {
                "challenge": make_challenge(user),
                "username": user.get_username(),
                "setup_required": not has_two_factor(user),
            }
        }
    )
