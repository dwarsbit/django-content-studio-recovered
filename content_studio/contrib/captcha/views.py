"""
The two endpoints of the Cap protocol, in the format of ``@cap.js/server``,
and the widget's solver.

- ``POST challenge``: ``{"challenge": {"c", "s", "d"}, "token", "expires"}``.
- ``POST redeem`` with ``{"token", "solutions"}``: ``{"success": true,
  "token", "expires"}``, or ``{"success": false, "error"}``.
"""

import secrets
from datetime import timedelta
from pathlib import Path

from django.http import FileResponse
from django.utils import timezone
from django.views.decorators.cache import cache_control
from django.views.decorators.http import require_safe
from rest_framework import exceptions
from rest_framework.parsers import JSONParser
from rest_framework.permissions import AllowAny
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response
from rest_framework.throttling import SimpleRateThrottle
from rest_framework.views import APIView

from content_studio.settings import cs_settings
from content_studio.throttling import ClientIPMixin

from . import pow
from .models import Challenge, Token
from .tokens import issue_token

CHALLENGE_LIFETIME = timedelta(minutes=10)
# The length of a puzzle's salt, in hex characters.
SALT_SIZE = 32
SOLVER = Path(__file__).with_name("solver.wasm")


class CaptchaThrottle(ClientIPMixin, SimpleRateThrottle):
    """
    Challenges and redeems together, per client IP address:
    CONTENT_STUDIO["CAPTCHA_THROTTLE_RATE"] (30/minute); None turns it off.
    """

    scope = "content_studio_captcha"

    def get_rate(self):
        return cs_settings.CAPTCHA_THROTTLE_RATE

    def get_cache_key(self, request, view):
        return self.cache_format % {
            "scope": self.scope,
            "ident": self.get_ident(request),
        }


class CapView(APIView):
    authentication_classes = []
    permission_classes = [AllowAny]
    throttle_classes = [CaptchaThrottle]
    parser_classes = [JSONParser]
    renderer_classes = [JSONRenderer]

    def handle_exception(self, exc):
        # The widget shows "error" of a failed response.
        response = super().handle_exception(exc)
        if isinstance(exc, exceptions.APIException):
            response.data = {"success": False, "error": str(exc.detail)}
        return response


class ChallengeView(CapView):
    def post(self, request):
        now = timezone.now()
        # Expired challenges and tokens go with every new challenge.
        Challenge.objects.filter(expires_at__lte=now).delete()
        Token.objects.filter(expires_at__lte=now).delete()

        challenge = Challenge.objects.create(
            token=secrets.token_hex(25),
            count=cs_settings.CAPTCHA_CHALLENGES,
            size=SALT_SIZE,
            difficulty=cs_settings.CAPTCHA_DIFFICULTY,
            expires_at=now + CHALLENGE_LIFETIME,
        )
        return Response(
            {
                "challenge": {
                    "c": challenge.count,
                    "s": challenge.size,
                    "d": challenge.difficulty,
                },
                "token": challenge.token,
                "expires": int(challenge.expires_at.timestamp() * 1000),
            }
        )


class RedeemView(CapView):
    def post(self, request):
        data = request.data if isinstance(request.data, dict) else {}
        token, solutions = data.get("token"), data.get("solutions")
        if not isinstance(token, str) or not isinstance(solutions, list):
            return Response({"success": False, "error": "Invalid body"}, status=400)

        challenge = Challenge.objects.filter(
            token=token, expires_at__gt=timezone.now()
        ).first()
        # A challenge is redeemed once, solved or not; the delete decides
        # between two requests with the same token.
        if challenge is None or Challenge.objects.filter(pk=token).delete()[0] == 0:
            return Response(
                {"success": False, "error": "Challenge invalid or expired"}, status=400
            )
        if not pow.check(
            token, challenge.count, challenge.size, challenge.difficulty, solutions
        ):
            return Response({"success": False, "error": "Invalid solution"}, status=400)

        value, expires = issue_token()
        return Response({"success": True, "token": value, "expires": expires})


@require_safe
@cache_control(public=True, max_age=86400)
def solver(request):
    """The widget's WebAssembly solver (``@cap.js/wasm``, Apache-2.0), so it loads from this site."""
    return FileResponse(SOLVER.open("rb"), content_type="application/wasm")
