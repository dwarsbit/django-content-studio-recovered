"""
The two-factor endpoints: the code step of the login (and setting up the
app there when it is required), and the profile page's card.
"""

from django.contrib.auth.signals import user_login_failed
from django.utils.translation import gettext as _
from django.utils.translation import ngettext
from rest_framework import status
from rest_framework.decorators import action
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.viewsets import ViewSet

from ...login import finish_login, has_two_factor, issue_session, two_factor_required
from ...permissions import IsActiveStaff
from ...settings import cs_settings
from ...signals import record_change
from . import service, totp
from .challenges import (
    InvalidChallenge,
    account_locked,
    count_account_failure,
    count_wrong_code,
    make_setup_token,
    read_challenge,
    read_setup_token,
    use_challenge,
)


def _text(request, name) -> str:
    value = request.data.get(name)

    return value if isinstance(value, str) else ""


def _error(message, status_code=status.HTTP_400_BAD_REQUEST):
    return Response({"detail": message}, status=status_code)


def _expired():
    return _error(_("This login has expired. Log in again."))


def _locked():
    return _error(
        _("Too many wrong codes. Wait a while, then log in again."),
        status.HTTP_429_TOO_MANY_REQUESTS,
    )


def _login_throttles():
    from ...login_backends import LoginRateThrottle

    return [LoginRateThrottle()] if cs_settings.LOGIN_THROTTLE_RATE else []


class TwoFactorLoginViewSet(ViewSet):
    """
    The code step after the password. The challenge from the password
    step is the gate; a right code starts the session.
    """

    authentication_classes = []
    permission_classes = [AllowAny]
    renderer_classes = [JSONRenderer]

    def get_throttles(self):
        return _login_throttles()

    def _wrong(self, request, user, nonce, message):
        """Count a wrong code; audit tools hear of it as a failed login."""
        count_account_failure(user)
        left = count_wrong_code(nonce)
        user_login_failed.send(
            sender=__name__,
            credentials={"username": user.get_username()},
            request=request._request,
        )

        if left == 0:
            return _error(_("Too many wrong codes. Log in again."))

        return _error(
            "%s %s"
            % (
                message,
                ngettext(
                    "You have %(count)d more try.",
                    "You have %(count)d more tries.",
                    left,
                )
                % {"count": left},
            )
        )

    @action(methods=["post"], detail=False, url_path="verify")
    def verify(self, request):
        """A code from the app, or a recovery code."""
        try:
            user, nonce = read_challenge(_text(request, "challenge"))
        except InvalidChallenge:
            return _expired()

        if not has_two_factor(user):
            return _expired()

        if account_locked(user):
            return _locked()

        recovery_code = _text(request, "recovery_code")

        if recovery_code:
            if not service.check_recovery_code(user, recovery_code):
                return self._wrong(
                    request, user, nonce, _("That recovery code is not right.")
                )
        elif not service.check_code(user, _text(request, "code")):
            return self._wrong(request, user, nonce, _("That code is not right."))

        if not use_challenge(nonce):
            return _expired()

        return finish_login(user, request, two_factor=True)

    @action(methods=["post"], detail=False, url_path="setup")
    def setup(self, request):
        """A new secret for a user who must set up two-factor login now."""
        try:
            user, nonce = read_challenge(_text(request, "challenge"))
        except InvalidChallenge:
            return _expired()

        if has_two_factor(user) or not two_factor_required(user):
            return _expired()

        secret = totp.generate_secret()

        return Response(
            {
                **service.setup_data(user, secret),
                "setup": make_setup_token(user, secret, nonce),
            }
        )

    @action(methods=["post"], detail=False, url_path="setup/confirm")
    def setup_confirm(self, request):
        """The first code from the app turns it on and starts the session;
        the recovery codes come with it, shown once."""
        try:
            user, nonce = read_challenge(_text(request, "challenge"))
            secret = read_setup_token(_text(request, "setup"), user, nonce)
        except InvalidChallenge:
            return _expired()

        if has_two_factor(user) or not two_factor_required(user):
            return _expired()

        if account_locked(user):
            return _locked()

        if totp.match_step(secret, _text(request, "code")) is None:
            return self._wrong(request, user, nonce, _("That code is not right."))

        if not use_challenge(nonce):
            return _expired()

        codes = service.enable(user, secret, _text(request, "code"))
        # Recorded as the user's own change: the login is theirs.
        request.user = user
        record_change(request, user, "updated", "Turned on two-factor login.")
        response = finish_login(user, request, two_factor=True)
        response.data["recovery_codes"] = codes

        return response


class TwoFactorCodeRateThrottle(UserRateThrottle):
    """Codes typed on the profile page are guesses too: they share the
    login rate limit, per user."""

    scope = "content_studio_two_factor_profile"

    def get_rate(self):
        return cs_settings.LOGIN_THROTTLE_RATE

    def allow_request(self, request, view):
        if not self.rate:
            return True

        return super().allow_request(request, view)


class TwoFactorProfileViewSet(ViewSet):
    """
    Two-factor login on the profile page: turn it on, new recovery codes,
    turn it off. Turning it on or off ends the user's other sessions;
    this one continues with the tokens in the response.
    """

    # Explicit, so the project's DEFAULT_PERMISSION_CLASSES never decide.
    permission_classes = [IsActiveStaff]
    renderer_classes = [JSONRenderer]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        backend = cs_settings.ADMIN_SITE.token_backend.active_backend
        self.authentication_classes = [backend.authentication_class]

    def get_throttles(self):
        if self.action == "setup":
            return []

        return [TwoFactorCodeRateThrottle()]

    @action(methods=["post"], detail=False, url_path="setup")
    def setup(self, request):
        user = request.user

        if has_two_factor(user):
            return _error(_("Two-factor login is already on."))

        secret = totp.generate_secret()

        return Response(
            {
                **service.setup_data(user, secret),
                "setup": make_setup_token(user, secret),
            }
        )

    @action(methods=["post"], detail=False, url_path="confirm")
    def confirm(self, request):
        user = request.user

        if has_two_factor(user):
            return _error(_("Two-factor login is already on."))

        try:
            secret = read_setup_token(_text(request, "setup"), user)
        except InvalidChallenge:
            return _error(_("This setup has expired. Start again."))

        # Turning it on locks out whoever lacks the app: a stolen session
        # alone must not do it, so the current password confirms it.
        from ...profile import check_current_password

        error = check_current_password(user, request)

        if error is not None:
            return error

        codes = service.enable(user, secret, _text(request, "code"))

        if codes is None:
            return Response(
                {"code": [_("That code is not right.")]},
                status=status.HTTP_400_BAD_REQUEST,
            )

        record_change(request, user, "updated", "Turned on two-factor login.")
        response = issue_session(user, request, two_factor=True)
        response.data["recovery_codes"] = codes

        return response

    def _check(self, request):
        """The app's current code, or a recovery code, confirms the
        request; an error response when neither is right."""
        user = request.user

        if not has_two_factor(user):
            return _error(_("Two-factor login is off."))

        if account_locked(user):
            return _locked()

        code = _text(request, "code")

        if service.check_code(user, code) or service.check_recovery_code(user, code):
            return None

        count_account_failure(user)

        return Response(
            {"code": [_("That code is not right.")]},
            status=status.HTTP_400_BAD_REQUEST,
        )

    @action(methods=["post"], detail=False, url_path="recovery-codes")
    def recovery_codes(self, request):
        error = self._check(request)

        if error is not None:
            return error

        codes = service.new_recovery_codes(request.user)
        record_change(request, request.user, "updated", "Made new recovery codes.")

        return Response({"recovery_codes": codes})

    @action(methods=["post"], detail=False, url_path="disable")
    def disable(self, request):
        user = request.user

        if two_factor_required(user):
            return _error(_("Two-factor login is required for your account."))

        error = self._check(request)

        if error is not None:
            return error

        service.disable(user)
        record_change(request, user, "updated", "Turned off two-factor login.")

        return issue_session(user, request, two_factor=False)


def set_up_router():
    from ...router import content_studio_router

    content_studio_router.register(
        "api/two-factor",
        TwoFactorLoginViewSet,
        basename="content_studio_two_factor_login",
    )
    content_studio_router.register(
        "api/profile/two-factor",
        TwoFactorProfileViewSet,
        basename="content_studio_two_factor_profile",
    )
