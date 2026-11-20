from django.contrib.auth import get_user_model, authenticate
from django.contrib.auth.signals import user_login_failed
from django.utils.translation import gettext as _
from rest_framework import serializers
from rest_framework.exceptions import PermissionDenied, Throttled
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.viewsets import ViewSet

from .. import login_failures
from ..utils import MAX_PASSWORD_LENGTH


def username_max_length():
    """The length of the user model's username field; a field without
    one gets the length of an email address."""
    user_model = get_user_model()
    field = user_model._meta.get_field(user_model.USERNAME_FIELD)

    return getattr(field, "max_length", None) or 254


class UsernamePasswordSerializer(serializers.Serializer):
    username = serializers.CharField(required=True)
    password = serializers.CharField(required=True, max_length=MAX_PASSWORD_LENGTH)

    def get_fields(self):
        fields = super().get_fields()
        # Bound here: the user model is not available at import time.
        fields["username"] = serializers.CharField(
            required=True, max_length=username_max_length()
        )

        return fields


class UsernamePasswordViewSet(ViewSet):
    """
    View set for username and password endpoints.
    """

    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def create(self, request):
        serializer = UsernamePasswordSerializer(data=request.data)

        serializer.is_valid(raise_exception=True)

        username = serializer.validated_data["username"]
        # The Django request, not DRF's wrapper: authentication backends
        # and signal receivers such as django-axes expect the former.
        django_request = request._request

        # Too many wrong passwords for this username, from any address:
        # refused before the password is checked, so guessing on cannot
        # tell a right password either (see login_failures.py).
        if login_failures.account_locked(username):
            user_login_failed.send(
                sender=__name__,
                credentials={"username": username},
                request=django_request,
            )

            raise Throttled(
                detail=_("Too many failed logins for this account. Try again later.")
            )

        user = UsernamePasswordBackend.login(
            username=username,
            password=serializer.validated_data["password"],
            request=django_request,
        )

        # Like the Django admin, only active staff users sign in; any
        # other outcome answers like a wrong password. authenticate()
        # reports its own failures; a user it accepts but the admin does
        # not is reported here, so audit tools see every refused login.
        if user is None or not (user.is_active and user.is_staff):
            if user is not None:
                user_login_failed.send(
                    sender=__name__,
                    credentials={"username": username},
                    request=django_request,
                )

            login_failures.count_failure(username)

            raise PermissionDenied(detail="Invalid username or password.")

        login_failures.clear_failures(username)

        from ..login import complete_login

        # The session, or the code step when two-factor login is on.
        return complete_login(user, request, backend=UsernamePasswordBackend)


class UsernamePasswordBackend:
    name = "Username password"
    view_set = UsernamePasswordViewSet

    @classmethod
    def get_info(cls):
        """
        Returns information about the backend.
        """
        user_model = get_user_model()
        username_field = getattr(user_model, user_model.USERNAME_FIELD, None)

        return {
            "type": cls.__name__,
            "config": {"username_field_type": username_field.field.__class__.__name__},
        }

    @classmethod
    def login(cls, username, password, request=None):
        """
        Authenticates user using username and password.
        Returns the user if successful, None otherwise.
        """
        return authenticate(request, username=username, password=password)
