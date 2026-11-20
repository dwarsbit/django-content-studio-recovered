"""
Tests for two-factor login (content_studio.contrib.two_factor): the TOTP
codes, the code step after the password, setting it up during login
when it is required, the profile card, an admin's reset, and how tokens
end when it changes.
"""

from unittest import mock

from django.contrib.admin.models import LogEntry
from django.contrib.auth import models as auth_models
from django.core import mail
from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from content_studio.checks import two_factor_errors
from content_studio.contrib.two_factor import service, totp
from content_studio.contrib.two_factor.models import (
    Authenticator,
    RecoveryCode,
    hash_recovery_code,
)
from content_studio.settings import cs_settings
from content_studio.token_backends.jwt import (
    REFRESH_COOKIE_NAME,
    create_access_token,
)

User = auth_models.User

PASSWORD = "Lantern-Secret-42"


def code(secret, offset=0):
    """The app's code, offset steps from now."""
    return totp.code_at(secret, totp.current_step() + offset)


def required(value):
    return mock.patch.object(cs_settings, "TWO_FACTOR_REQUIRED", value)


def bearer(access):
    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {access}")
    return client


# RFC 6238 appendix B: the SHA-1 secret and its 8-digit codes.
RFC_SECRET = "12345678901234567890"


def test_totp_matches_the_rfc_6238_vectors():
    key = RFC_SECRET.encode()
    vectors = {
        59: "94287082",
        1111111109: "07081804",
        1111111111: "14050471",
        1234567890: "89005924",
        2000000000: "69279037",
        20000000000: "65353130",
    }

    for seconds, expected in vectors.items():
        assert totp.hotp(key, seconds // totp.STEP, digits=8) == expected


def test_hotp_matches_the_rfc_4226_vectors():
    key = RFC_SECRET.encode()
    expected = ["755224", "287082", "359152", "969429", "338314"]

    assert [totp.hotp(key, counter) for counter in range(5)] == expected


def test_a_code_matches_its_step_and_the_ones_beside_it():
    secret = totp.generate_secret()
    now = 1_800_000_000
    step = totp.current_step(now)

    assert totp.match_step(secret, totp.code_at(secret, step), now=now) == step
    assert totp.match_step(secret, totp.code_at(secret, step - 1), now=now) == step - 1
    assert totp.match_step(secret, totp.code_at(secret, step + 1), now=now) == step + 1
    assert totp.match_step(secret, totp.code_at(secret, step + 2), now=now) is None
    # A code works once: not again at or before the last step used.
    assert (
        totp.match_step(secret, totp.code_at(secret, step), after=step, now=now) is None
    )
    assert totp.match_step(secret, "12345", now=now) is None
    assert totp.match_step(secret, "abcdef", now=now) is None


def test_secrets_are_160_bits_of_base32():
    secret = totp.generate_secret()

    assert len(secret) == 32
    assert len(totp._key(secret)) == 20


def test_provisioning_uri():
    uri = totp.provisioning_uri("JBSWY3DPEHPK3PXP", "maya@example.com", "North bound")

    assert uri == (
        "otpauth://totp/North%20bound:maya@example.com"
        "?secret=JBSWY3DPEHPK3PXP&digits=6&period=30&issuer=North%20bound"
    )


class TwoFactorTestCase(TestCase):
    def setUp(self):
        cache.clear()
        self.user = User.objects.create_user(
            username="maya",
            password=PASSWORD,
            email="maya@example.com",
            first_name="Maya",
            is_staff=True,
        )
        self.anonymous = APIClient()

    def enable(self, user=None):
        """Turn it on for the user; returns the secret and the codes."""
        user = user or self.user
        secret = totp.generate_secret()
        codes = service.enable(user, secret, code(secret))
        return secret, codes

    def login(self, username="maya", password=PASSWORD):
        return self.anonymous.post(
            "/api/login/usernamepassword",
            {"username": username, "password": password},
            format="json",
        )

    def challenge(self, **kwargs):
        response = self.login(**kwargs)
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["two_factor"]["challenge"]

    def verify(self, challenge, **data):
        return self.anonymous.post(
            "/api/two-factor/verify", {"challenge": challenge, **data}, format="json"
        )


class LoginTests(TwoFactorTestCase):
    def test_without_two_factor_the_password_starts_the_session(self):
        response = self.login()

        self.assertIn("access", response.json())
        self.assertIn(REFRESH_COOKIE_NAME, response.cookies)

    def test_with_two_factor_the_password_answers_a_challenge(self):
        self.enable()

        response = self.login()

        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertNotIn("access", body)
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(body["two_factor"]["username"], "maya")
        self.assertFalse(body["two_factor"]["setup_required"])

    def test_a_wrong_password_still_answers_like_before(self):
        self.enable()

        response = self.login(password="wrong")

        self.assertEqual(response.status_code, 403)

    def test_the_right_code_starts_the_session(self):
        from django.contrib.auth.signals import user_logged_in

        secret, _ = self.enable()
        challenge = self.challenge()
        received = []

        def receiver(**kwargs):
            received.append(kwargs["user"])

        user_logged_in.connect(receiver)
        try:
            response = self.verify(challenge, code=code(secret, 1))
        finally:
            user_logged_in.disconnect(receiver)

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("access", response.json())
        self.assertIn(REFRESH_COOKIE_NAME, response.cookies)
        self.assertEqual(received, [self.user])
        self.assertEqual(
            bearer(response.json()["access"]).get("/api/profile").status_code, 200
        )

    def test_a_wrong_code_counts_down(self):
        self.enable()
        challenge = self.challenge()

        response = self.verify(challenge, code="000000")

        self.assertEqual(response.status_code, 400)
        self.assertIn("4 more tries", response.json()["detail"])

    def test_five_wrong_codes_void_the_challenge(self):
        secret, _ = self.enable()
        challenge = self.challenge()

        for _ in range(5):
            self.verify(challenge, code="000000")

        response = self.verify(challenge, code=code(secret, 1))

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access", response.json())

    def test_a_challenge_works_once(self):
        secret, _ = self.enable()
        challenge = self.challenge()
        self.verify(challenge, code=code(secret, 1))

        response = self.verify(challenge, code=code(secret, 1))

        self.assertEqual(response.status_code, 400)

    def test_a_code_works_once(self):
        secret, _ = self.enable()
        self.verify(self.challenge(), code=code(secret, 1))

        response = self.verify(self.challenge(), code=code(secret, 1))

        self.assertEqual(response.status_code, 400)

    def test_a_password_change_voids_the_challenge(self):
        secret, _ = self.enable()
        challenge = self.challenge()
        self.user.set_password("Other-Secret-42")
        self.user.save()

        response = self.verify(challenge, code=code(secret, 1))

        self.assertEqual(response.status_code, 400)

    def test_a_forged_challenge_is_refused(self):
        secret, _ = self.enable()

        response = self.verify("forged", code=code(secret, 1))

        self.assertEqual(response.status_code, 400)

    def test_a_recovery_code_works_once(self):
        _, codes = self.enable()

        response = self.verify(self.challenge(), recovery_code=codes[0].upper())
        self.assertEqual(response.status_code, 200, response.content)

        response = self.verify(self.challenge(), recovery_code=codes[0])
        self.assertEqual(response.status_code, 400)

    def test_recovery_codes_are_stored_as_hmacs(self):
        _, codes = self.enable()

        stored = set(RecoveryCode.objects.values_list("code_hash", flat=True))

        self.assertEqual(len(codes), 10)
        self.assertEqual(stored, {hash_recovery_code(c) for c in codes})
        self.assertFalse(stored & set(codes))

    def test_wrong_codes_lock_the_account(self):
        secret, _ = self.enable()

        with mock.patch.object(cs_settings, "TWO_FACTOR_THROTTLE_RATE", "3/hour"):
            for _ in range(3):
                self.verify(self.challenge(), code="000000")

            response = self.verify(self.challenge(), code=code(secret, 1))

        self.assertEqual(response.status_code, 429)

    def test_wrong_codes_report_failed_logins(self):
        from django.contrib.auth.signals import user_login_failed

        self.enable()
        challenge = self.challenge()
        failed = []

        def receiver(**kwargs):
            failed.append(kwargs["credentials"])

        user_login_failed.connect(receiver)
        try:
            self.verify(challenge, code="000000")
        finally:
            user_login_failed.disconnect(receiver)

        self.assertEqual(failed, [{"username": "maya"}])


class RequiredTests(TwoFactorTestCase):
    def setup(self, challenge):
        return self.anonymous.post(
            "/api/two-factor/setup", {"challenge": challenge}, format="json"
        )

    def test_a_user_without_it_sets_it_up_during_login(self):
        with required("all"):
            response = self.login()
            self.assertTrue(response.json()["two_factor"]["setup_required"])
            challenge = response.json()["two_factor"]["challenge"]

            setup = self.setup(challenge).json()
            self.assertIn("otpauth://totp/", setup["uri"])

            wrong = self.anonymous.post(
                "/api/two-factor/setup/confirm",
                {"challenge": challenge, "setup": setup["setup"], "code": "000000"},
                format="json",
            )
            self.assertEqual(wrong.status_code, 400)

            response = self.anonymous.post(
                "/api/two-factor/setup/confirm",
                {
                    "challenge": challenge,
                    "setup": setup["setup"],
                    "code": code(setup["secret"]),
                },
                format="json",
            )

            self.assertEqual(response.status_code, 200, response.content)
            self.assertEqual(len(response.json()["recovery_codes"]), 10)
            self.assertTrue(Authenticator.objects.filter(user=self.user).exists())
            self.assertEqual(
                bearer(response.json()["access"]).get("/api/profile").status_code,
                200,
            )

    def test_setup_is_refused_when_not_required(self):
        secret, _ = self.enable()
        response = self.setup(self.challenge())

        self.assertEqual(response.status_code, 400)

    def test_a_setup_token_belongs_to_its_login(self):
        other = User.objects.create_user(
            username="jonas", password=PASSWORD, is_staff=True
        )

        with required("all"):
            setup = self.setup(self.challenge()).json()
            challenge = self.challenge(username="jonas")
            response = self.anonymous.post(
                "/api/two-factor/setup/confirm",
                {
                    "challenge": challenge,
                    "setup": setup["setup"],
                    "code": code(setup["secret"]),
                },
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertFalse(Authenticator.objects.filter(user=other).exists())

    def test_superusers_only(self):
        User.objects.create_superuser(
            username="admin", password=PASSWORD, email="admin@example.com"
        )

        with required("superusers"):
            self.assertIn("access", self.login().json())
            self.assertIn("two_factor", self.login(username="admin").json())

    def test_requiring_it_ends_sessions_that_skipped_the_code(self):
        client = bearer(create_access_token(self.user))
        self.assertEqual(client.get("/api/profile").status_code, 200)

        with required("all"):
            self.assertEqual(client.get("/api/profile").status_code, 401)

    def test_a_session_with_the_code_continues_when_required(self):
        secret, _ = self.enable()
        access = self.verify(self.challenge(), code=code(secret, 1)).json()["access"]

        with required("all"):
            self.assertEqual(bearer(access).get("/api/profile").status_code, 200)

    def test_refresh_keeps_the_code_step(self):
        secret, _ = self.enable()
        self.verify(self.challenge(), code=code(secret, 1))

        response = self.anonymous.post("/api/tokens/jsonwebtoken/refresh")

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            bearer(response.json()["access"]).get("/api/profile").status_code, 200
        )


class SessionTests(TwoFactorTestCase):
    def test_turning_it_on_ends_other_sessions(self):
        client = bearer(create_access_token(self.user))

        self.enable()

        self.assertEqual(client.get("/api/profile").status_code, 401)

    def test_a_reset_ends_the_sessions(self):
        secret, _ = self.enable()
        access = self.verify(self.challenge(), code=code(secret, 1)).json()["access"]

        service.disable(User.objects.get(pk=self.user.pk))

        self.assertEqual(bearer(access).get("/api/profile").status_code, 401)

    def test_new_recovery_codes_keep_the_sessions(self):
        secret, _ = self.enable()
        access = self.verify(self.challenge(), code=code(secret, 1)).json()["access"]

        service.new_recovery_codes(self.user)

        self.assertEqual(bearer(access).get("/api/profile").status_code, 200)


class ProfileTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.client = bearer(create_access_token(self.user))

    def logged_in_with_two_factor(self):
        """Logged in with a recovery code, so the app's next code is left
        for the test."""
        secret, codes = self.enable()
        access = self.verify(self.challenge(), recovery_code=codes.pop()).json()[
            "access"
        ]
        self.client = bearer(access)
        return secret, codes

    def test_profile_shows_the_state(self):
        state = self.client.get("/api/profile").json()["two_factor"]

        self.assertEqual(
            state,
            {
                "enabled": False,
                "since": None,
                "recovery_codes_left": 0,
                "required": False,
            },
        )

    def test_turn_it_on(self):
        setup = self.client.post("/api/profile/two-factor/setup").json()

        response = self.client.post(
            "/api/profile/two-factor/confirm",
            {"setup": setup["setup"], "code": code(setup["secret"])},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(len(response.json()["recovery_codes"]), 10)
        # The old session ended; the one in the response continues.
        self.assertEqual(self.client.get("/api/profile").status_code, 401)
        state = (
            bearer(response.json()["access"]).get("/api/profile").json()["two_factor"]
        )
        self.assertTrue(state["enabled"])
        self.assertEqual(state["recovery_codes_left"], 10)
        self.assertTrue(
            LogEntry.objects.filter(
                change_message="Turned on two-factor login."
            ).exists()
        )

    def test_a_wrong_first_code_turns_nothing_on(self):
        setup = self.client.post("/api/profile/two-factor/setup").json()

        response = self.client.post(
            "/api/profile/two-factor/confirm",
            {"setup": setup["setup"], "code": "000000"},
            format="json",
        )

        self.assertEqual(response.status_code, 400)
        self.assertIn("code", response.json())
        self.assertFalse(Authenticator.objects.exists())

    def test_a_setup_token_of_another_user_is_refused(self):
        other = User.objects.create_user(
            username="jonas", password=PASSWORD, is_staff=True
        )
        setup = bearer(create_access_token(other)).post("/api/profile/two-factor/setup")

        response = self.client.post(
            "/api/profile/two-factor/confirm",
            {"setup": setup.json()["setup"], "code": code(setup.json()["secret"])},
            format="json",
        )

        self.assertEqual(response.status_code, 400)

    def test_new_recovery_codes_need_a_code(self):
        secret, codes = self.logged_in_with_two_factor()

        wrong = self.client.post(
            "/api/profile/two-factor/recovery-codes", {"code": "000000"}, format="json"
        )
        self.assertEqual(wrong.status_code, 400)

        response = self.client.post(
            "/api/profile/two-factor/recovery-codes",
            {"code": code(secret, 1)},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(set(response.json()["recovery_codes"]) & set(codes))

    def test_turn_it_off_with_a_recovery_code(self):
        _, codes = self.logged_in_with_two_factor()

        response = self.client.post(
            "/api/profile/two-factor/disable", {"code": codes[3]}, format="json"
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(Authenticator.objects.exists())
        self.assertFalse(RecoveryCode.objects.exists())
        self.assertEqual(
            bearer(response.json()["access"]).get("/api/profile").status_code, 200
        )

    def test_it_cannot_be_turned_off_when_required(self):
        secret, _ = self.logged_in_with_two_factor()

        with required("all"):
            response = self.client.post(
                "/api/profile/two-factor/disable",
                {"code": code(secret, 1)},
                format="json",
            )

        self.assertEqual(response.status_code, 400)
        self.assertTrue(Authenticator.objects.exists())

    def test_a_password_change_keeps_the_code_step(self):
        self.logged_in_with_two_factor()

        response = self.client.post(
            "/api/profile/password",
            {"current_password": PASSWORD, "new_password": "New-Secret-4242"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(
            bearer(response.json()["access"]).get("/api/profile").status_code, 200
        )


class ResetTests(TwoFactorTestCase):
    def setUp(self):
        super().setUp()
        self.admin = User.objects.create_superuser(
            username="admin",
            password=PASSWORD,
            email="admin@example.com",
            first_name="Leon",
        )
        self.client = bearer(create_access_token(self.admin))

    def reset(self, user, client=None):
        with self.captureOnCommitCallbacks(execute=True):
            return (client or self.client).post(
                f"/api/content/auth.user/{user.pk}/two-factor/reset"
            )

    def test_reset_turns_it_off_and_emails_the_user(self):
        self.enable()

        response = self.reset(self.user)

        self.assertEqual(response.status_code, 204)
        self.assertFalse(Authenticator.objects.filter(user=self.user).exists())
        self.assertEqual(len(mail.outbox), 1)
        self.assertEqual(mail.outbox[0].to, ["maya@example.com"])
        self.assertIn("Leon reset your two-factor login", mail.outbox[0].body)
        self.assertTrue(
            LogEntry.objects.filter(change_message="Reset two-factor login.").exists()
        )

    def test_the_edit_page_offers_it_while_it_is_on(self):
        url = f"/api/content/auth.user/{self.user.pk}"
        self.assertFalse(
            self.client.get(url).json()["__user__"]["can_reset_two_factor"]
        )

        self.enable()

        self.assertTrue(self.client.get(url).json()["__user__"]["can_reset_two_factor"])

    def test_not_when_it_is_off(self):
        self.assertEqual(self.reset(self.user).status_code, 403)

    def test_needs_change_permission(self):
        self.enable()
        editor = User.objects.create_user(
            username="sam", password=PASSWORD, is_staff=True
        )
        editor.user_permissions.set(
            auth_models.Permission.objects.filter(codename="view_user")
        )

        response = self.reset(self.user, bearer(create_access_token(editor)))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Authenticator.objects.filter(user=self.user).exists())

    def test_only_a_superuser_resets_a_superuser(self):
        self.enable(self.admin)
        editor = User.objects.create_user(
            username="sam", password=PASSWORD, is_staff=True
        )
        editor.user_permissions.set(
            auth_models.Permission.objects.filter(
                codename__in=["view_user", "change_user"]
            )
        )

        response = self.reset(self.admin, bearer(create_access_token(editor)))

        self.assertEqual(response.status_code, 403)

    def test_not_for_an_account_with_more_permissions(self):
        editor = User.objects.create_user(
            username="sam", password=PASSWORD, is_staff=True
        )
        editor.user_permissions.set(
            auth_models.Permission.objects.filter(
                codename__in=["view_user", "change_user"]
            )
        )
        self.user.user_permissions.set(
            auth_models.Permission.objects.filter(codename="delete_user")
        )
        self.enable()

        response = self.reset(self.user, bearer(create_access_token(editor)))

        self.assertEqual(response.status_code, 403)
        self.assertTrue(Authenticator.objects.filter(user=self.user).exists())

    def test_not_the_own(self):
        secret, _ = self.enable(self.admin)
        access = self.verify(
            self.challenge(username="admin"), code=code(secret, 1)
        ).json()["access"]

        response = self.reset(self.admin, bearer(access))

        self.assertEqual(response.status_code, 403)

    def test_status_callout_on_the_edit_page(self):
        from content_studio.user_studios import TwoFactorStatus

        callout = TwoFactorStatus()
        request = mock.Mock(user=self.admin)

        self.assertIsNone(callout.get_text(self.user, request))

        self.enable()

        self.assertIn("Reset two-factor login", callout.get_text(self.user, request))


class SetPasswordLinkTests(TwoFactorTestCase):
    def test_a_link_leads_to_the_code_step(self):
        from content_studio.password_links import make_link

        secret, _ = self.enable()

        with mock.patch.object(cs_settings, "ADMIN_URL", "http://testserver/"):
            query = make_link(self.user).split("?", 1)[1]
        link = dict(part.split("=", 1) for part in query.split("&"))

        response = self.anonymous.post(
            "/api/set-password",
            {**link, "password": "Fresh-Secret-4242"},
            format="json",
        )

        self.assertEqual(response.status_code, 200, response.content)
        self.assertIn("two_factor", response.json())
        self.assertNotIn(REFRESH_COOKIE_NAME, response.cookies)

        response = self.verify(
            response.json()["two_factor"]["challenge"], code=code(secret, 1)
        )
        self.assertIn("access", response.json())


class CheckTests(TestCase):
    def test_valid_settings(self):
        for value in (None, "superusers", "all"):
            with required(value):
                self.assertEqual(two_factor_errors(), [])

    def test_unknown_value(self):
        with required("everyone"):
            self.assertEqual(two_factor_errors()[0][0], "content_studio.E044")

    def test_needs_the_app(self):
        with (
            required("all"),
            mock.patch("django.apps.apps.is_installed", return_value=False),
        ):
            self.assertEqual(two_factor_errors()[0][0], "content_studio.E044")

    def test_rate(self):
        with mock.patch.object(cs_settings, "TWO_FACTOR_THROTTLE_RATE", "lots"):
            self.assertEqual(two_factor_errors()[0][0], "content_studio.E044")


@override_settings(LANGUAGE_CODE="en")
class IssuerTests(TestCase):
    def test_defaults_to_the_site_title(self):
        with mock.patch.object(cs_settings.ADMIN_SITE, "site_title", "Northbound"):
            self.assertEqual(service.issuer(), "Northbound")

    def test_setting(self):
        with mock.patch.object(cs_settings, "TWO_FACTOR_ISSUER", "Acme"):
            self.assertEqual(service.issuer(), "Acme")
