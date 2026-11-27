"""
The captcha (content_studio.contrib.captcha): the Cap endpoints, the
proof of work, one-time tokens, the DRF and Django forms fields, the
widget, its CSP and the system checks. Ported from DjangoStack's tests.
"""

import base64
import hashlib
from datetime import timedelta
from pathlib import Path

import pytest
from django import forms
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured
from django.test import override_settings
from django.utils import timezone
from rest_framework import serializers
from rest_framework.test import APIClient

from content_studio.contrib.captcha import verify_captcha
from content_studio.contrib.captcha import checks as captcha_checks
from content_studio.contrib.captcha.fields import CaptchaField
from content_studio.contrib.captcha.forms import (
    CAPTCHA_CSP,
    CAPTCHA_STYLE_HASH,
    CaptchaField as FormCaptchaField,
    CaptchaWidget,
)
from content_studio.contrib.captcha.models import Challenge, Token
from content_studio.contrib.captcha.pow import check, prng, solve
from content_studio.contrib.captcha.testing import captcha_token
from content_studio.contrib.settings import sections
from content_studio.contrib.settings.env import Env

pytestmark = pytest.mark.django_db

APP = Path(__file__).parent.parent / "content_studio" / "contrib" / "captcha"


def studio_settings(settings, **values):
    settings.CONTENT_STUDIO = {**getattr(settings, "CONTENT_STUDIO", {}), **values}


@pytest.fixture(autouse=True)
def easy(settings):
    """Few, easy puzzles, so a test solves a challenge in milliseconds."""
    cache.clear()
    studio_settings(settings, CAPTCHA_CHALLENGES=3, CAPTCHA_DIFFICULTY=2)


@pytest.fixture
def client():
    return APIClient()


@pytest.fixture
def no_captcha(settings):
    studio_settings(settings, CAPTCHA=False)


def redeem(client):
    challenge = client.post("/api/cap/challenge").json()
    c, s, d = (challenge["challenge"][key] for key in ("c", "s", "d"))
    solutions = solve(challenge["token"], c, s, d)
    return client.post(
        "/api/cap/redeem",
        {"token": challenge["token"], "solutions": solutions},
        format="json",
    )


def test_prng_matches_cap():
    # Values of prng() in @cap.js/server 4.0.5.
    assert prng("abc1", 32) == "a240feb00f42af1b0e9dab2bc4ea4c37"
    assert prng("x50d", 32) == "d5d68b06927f62fdba3f404d14efe396"
    assert prng("ffffd", 4) == "0d57"


def test_challenge_format(client):
    response = client.post("/api/cap/challenge")
    assert response.status_code == 200
    data = response.json()
    assert data["challenge"] == {"c": 3, "s": 32, "d": 2}
    assert len(data["token"]) == 50
    assert data["expires"] > timezone.now().timestamp() * 1000
    assert Challenge.objects.filter(pk=data["token"]).exists()


def test_challenge_needs_no_csrf_or_login():
    client = APIClient(enforce_csrf_checks=True)
    assert client.post("/api/cap/challenge").status_code == 200


def test_redeem_gives_a_token_once(client):
    response = redeem(client)
    assert response.status_code == 200
    data = response.json()
    assert data["success"] is True
    token_id, secret = data["token"].split(":")
    assert len(token_id) == 16 and len(secret) == 30
    assert data["expires"] > timezone.now().timestamp() * 1000
    assert Challenge.objects.count() == 0

    assert verify_captcha(data["token"]) is True
    assert verify_captcha(data["token"]) is False


def test_only_the_digest_of_the_secret_is_stored(client):
    token = redeem(client).json()["token"]
    token_id, secret = token.split(":")
    row = Token.objects.get(pk=token_id)
    assert row.digest == hashlib.sha256(secret.encode()).hexdigest()
    assert secret not in row.digest


def test_wrong_solution_is_refused(client):
    challenge = client.post("/api/cap/challenge").json()
    c, s, d = (challenge["challenge"][key] for key in ("c", "s", "d"))
    solutions = solve(challenge["token"], c, s, d)
    wrong = [solutions[0] + 1, *solutions[1:]]
    if check(challenge["token"], c, s, d, wrong):  # pragma: no cover - unlikely
        pytest.skip("the changed number solves the puzzle too")
    response = client.post(
        "/api/cap/redeem",
        {"token": challenge["token"], "solutions": wrong},
        format="json",
    )
    assert response.status_code == 400
    assert response.json() == {"success": False, "error": "Invalid solution"}
    # The challenge is gone: the right solutions no longer help.
    response = client.post(
        "/api/cap/redeem",
        {"token": challenge["token"], "solutions": solutions},
        format="json",
    )
    assert response.json()["error"] == "Challenge invalid or expired"


@pytest.mark.parametrize(
    "body",
    [
        {},
        {"token": "x"},
        {"token": "x", "solutions": "1,2"},
        {"token": 1, "solutions": []},
    ],
)
def test_invalid_body(client, body):
    response = client.post("/api/cap/redeem", body, format="json")
    assert response.status_code == 400
    assert response.json()["success"] is False


def test_malformed_json_is_an_error_the_widget_shows(client):
    response = client.post(
        "/api/cap/redeem", data="{not json", content_type="application/json"
    )
    assert response.status_code == 400
    assert response.json()["success"] is False
    assert response.json()["error"]


def test_check_refuses_other_types():
    assert check("t", 2, 32, 1, [1]) is False
    assert check("t", 1, 32, 1, [True]) is False
    assert check("t", 1, 32, 1, [1.5]) is False
    assert check("t", 1, 32, 1, ["1"]) is False
    assert check("t", 1, 32, 1, [-1]) is False
    assert check("t", 1, 32, 1, "1") is False


def test_expired_challenge_and_token(client):
    challenge = client.post("/api/cap/challenge").json()
    Challenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    response = client.post(
        "/api/cap/redeem",
        {"token": challenge["token"], "solutions": [0, 0, 0]},
        format="json",
    )
    assert response.json()["error"] == "Challenge invalid or expired"

    token = redeem(client).json()["token"]
    Token.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    assert verify_captcha(token) is False


def test_expired_rows_are_deleted(client):
    client.post("/api/cap/challenge")
    redeem(client)
    Challenge.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    Token.objects.update(expires_at=timezone.now() - timedelta(seconds=1))
    client.post("/api/cap/challenge")
    assert Challenge.objects.count() == 1
    assert Token.objects.count() == 0


@pytest.mark.parametrize(
    "token", [None, 1, "", "abc", ":abc", "abc:", "a:b", "x" * 200]
)
def test_bad_tokens(token):
    assert verify_captcha(token) is False


def test_throttle(client):
    codes = [client.post("/api/cap/challenge").status_code for _ in range(31)]
    assert codes.count(200) == 30
    assert codes[-1] == 429
    response = client.post("/api/cap/redeem", {}, format="json")
    assert response.status_code == 429
    assert response.json()["success"] is False


def test_throttle_ignores_a_spoofed_forwarded_for(client):
    for number in range(30):
        client.post("/api/cap/challenge", HTTP_X_FORWARDED_FOR=f"10.0.0.{number}")
    response = client.post("/api/cap/challenge", HTTP_X_FORWARDED_FOR="10.0.1.1")
    assert response.status_code == 429


def test_throttle_rate_setting(client, settings):
    studio_settings(settings, CAPTCHA_THROTTLE_RATE="2/minute")
    codes = [client.post("/api/cap/challenge").status_code for _ in range(3)]
    assert codes == [200, 200, 429]

    studio_settings(settings, CAPTCHA_THROTTLE_RATE=None)
    cache.clear()
    assert all(client.post("/api/cap/challenge").status_code == 200 for _ in range(40))


def test_solver(client):
    response = client.get("/api/cap/solver.wasm")
    assert response.status_code == 200
    assert response["Content-Type"] == "application/wasm"
    assert "public" in response["Cache-Control"]
    assert "max-age=86400" in response["Cache-Control"]
    assert b"".join(response.streaming_content).startswith(b"\0asm")


def test_solver_is_get_only(client):
    assert client.post("/api/cap/solver.wasm").status_code == 405


def test_captcha_off(no_captcha):
    assert verify_captcha("anything") is True
    assert verify_captcha(None) is True


def test_captcha_field(client):
    class Signup(serializers.Serializer):
        email = serializers.EmailField()
        captcha = CaptchaField()

    token = redeem(client).json()["token"]
    serializer = Signup(data={"email": "a@example.com", "captcha": token})
    assert serializer.is_valid(), serializer.errors
    assert serializer.validated_data["captcha"] == token
    assert "captcha" not in Signup(serializer.validated_data).data

    # Used up.
    serializer = Signup(data={"email": "a@example.com", "captcha": token})
    assert not serializer.is_valid()
    assert "captcha" in serializer.errors

    serializer = Signup(data={"email": "a@example.com"})
    assert not serializer.is_valid()
    assert serializer.errors["captcha"] == ["Verify that you are human."]

    serializer = Signup(data={"email": "a@example.com", "captcha": ""})
    assert not serializer.is_valid()
    assert serializer.errors["captcha"] == ["Verify that you are human."]

    serializer = Signup(data={"email": "a@example.com", "captcha": "a:b"})
    assert not serializer.is_valid()
    assert "not valid" in str(serializer.errors["captcha"][0])

    serializer = Signup(data={"email": "a@example.com", "captcha": "x" * 101})
    assert not serializer.is_valid()


def test_captcha_field_off(no_captcha):
    class Signup(serializers.Serializer):
        captcha = CaptchaField()

    assert Signup(data={"captcha": "anything"}).is_valid()


def test_testing_token():
    token = captcha_token()
    assert verify_captcha(token) is True
    assert verify_captcha(token) is False


# The Django forms field and widget.


class ContactForm(forms.Form):
    email = forms.EmailField()
    captcha = FormCaptchaField()


def test_widget_renders_the_cap_element():
    html = str(ContactForm()["captcha"])
    assert html == (
        '<cap-widget id="id_captcha" data-cap-api-endpoint="/api/cap/" '
        'data-cap-hidden-field-name="captcha"></cap-widget>'
    )
    assert "required" not in html


def test_widget_follows_the_include_path():
    with override_settings(ROOT_URLCONF="tests.captcha_prefixed_urls"):
        form = ContactForm()
        assert 'data-cap-api-endpoint="/forms/captcha/"' in str(form["captcha"])
        assert 'data-solver-url="/forms/captcha/solver.wasm"' in str(form.media)


def test_widget_media():
    media = str(ContactForm().media)
    loader = media.index("content_studio/captcha/loader.js")
    widget = media.index("content_studio/captcha/cap.min.js")
    assert loader < widget
    assert 'data-solver-url="/api/cap/solver.wasm"' in media
    assert media.count("defer") == 2


def test_form_field_end_to_end(client):
    token = redeem(client).json()["token"]
    form = ContactForm(data={"email": "a@example.com", "captcha": token})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["captcha"] == token

    form = ContactForm(data={"email": "a@example.com", "captcha": token})
    assert not form.is_valid()
    assert form.errors["captcha"] == [
        "The captcha is not valid or has expired. Verify that you are human and try again."
    ]

    form = ContactForm(data={"email": "a@example.com"})
    assert form.errors["captcha"] == ["Verify that you are human."]


def test_form_field_off(no_captcha):
    form = ContactForm(data={"email": "a@example.com"})
    assert form.is_valid(), form.errors
    assert form.cleaned_data["captcha"] == ""
    assert str(form["captcha"]) == ""
    assert str(form.media) == ""


def test_style_hash_matches_the_vendored_widget():
    """CAPTCHA_STYLE_HASH is the hash of the <style> the widget adds to its shadow root."""
    # The widget sets its shadow root to <style>CSS</style>; the hash is of the CSS.
    source = (APP / "static" / "content_studio" / "captcha" / "cap.min.js").read_text()
    tag = source.index("innerHTML=`<style${")
    start = source.index('""}>', tag) + 4
    css = source[start : source.index("</style>", start)]
    assert css.startswith(":host{")
    digest = base64.b64encode(hashlib.sha256(css.encode()).digest()).decode()
    assert f"'sha256-{digest}'" == CAPTCHA_STYLE_HASH
    assert CAPTCHA_CSP["style-src"] == (CAPTCHA_STYLE_HASH,)
    assert CAPTCHA_CSP["script-src"] == ("'wasm-unsafe-eval'",)
    assert CAPTCHA_CSP["worker-src"] == ("'self'", "blob:")
    assert CAPTCHA_CSP["img-src"] == ("data:",)


def test_notice_names_the_vendored_files():
    notice = (APP / "NOTICE").read_text()
    assert "solver.wasm" in notice and "@cap.js/wasm 0.0.8" in notice
    assert "cap.min.js" in notice and "@cap.js/widget" in notice and "0.1.58" in notice
    assert "Apache License 2.0" in notice


# Settings and system checks.


def test_configure_reads_captcha_variables():
    def run(environ):
        ctx = sections.Context(
            env=Env(environ),
            base_dir=Path("/tmp"),
            namespace={},
            settings={},
            debug=False,
            project_name="p",
            site_url="https://example.com",
            backend_url="https://example.com",
        )
        return sections.content_studio(ctx)["CONTENT_STUDIO"]

    defaults = run({})
    assert defaults["CAPTCHA"] is True
    assert defaults["CAPTCHA_THROTTLE_RATE"] == "30/minute"

    configured = run({"CAPTCHA": "off", "CAPTCHA_THROTTLE_RATE": "5/minute"})
    assert configured["CAPTCHA"] is False
    assert configured["CAPTCHA_THROTTLE_RATE"] == "5/minute"

    with pytest.raises(ImproperlyConfigured, match="CAPTCHA must be on or off"):
        run({"CAPTCHA": "yes"})


def test_check_settings_clean():
    assert captcha_checks.check_captcha_settings() == []


@pytest.mark.parametrize(
    "values, fragment",
    [
        ({"CAPTCHA": "off"}, "CAPTCHA must be True or False"),
        ({"CAPTCHA_CHALLENGES": 0}, "CAPTCHA_CHALLENGES must be"),
        ({"CAPTCHA_CHALLENGES": "50"}, "CAPTCHA_CHALLENGES must be"),
        ({"CAPTCHA_DIFFICULTY": 9}, "CAPTCHA_DIFFICULTY must be"),
        ({"CAPTCHA_DIFFICULTY": True}, "CAPTCHA_DIFFICULTY must be"),
        ({"CAPTCHA_THROTTLE_RATE": "lots"}, "CAPTCHA_THROTTLE_RATE must be"),
    ],
)
def test_check_settings_errors(settings, values, fragment):
    studio_settings(settings, **values)
    messages = captcha_checks.check_captcha_settings()
    assert [m.id for m in messages] == ["content_studio.E066"]
    assert fragment in messages[0].msg


def test_check_urls():
    assert captcha_checks.check_captcha_urls() == []
    with override_settings(ROOT_URLCONF="content_studio.urls"):
        messages = captcha_checks.check_captcha_urls()
    assert [m.id for m in messages] == ["content_studio.W043"]
