from unittest import mock

from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from users.choices import TokenVersionChoices
from users.models import Token, User

from social_core.backends.open_id_connect import OpenIdConnectAuth

from netbox_sso_redirect.middleware import SSORedirectMiddleware

BRIDGE = "netbox_sso_redirect/bridge.html"
OFF = {"netbox_sso_redirect": {"backend": "oidc", "local_param": "local", "local_login": False}}
CREDS = {"username": "admin", "password": "admin-pass-123"}
IDP = {"authorization_endpoint": "https://idp.example/authorize"}


class LocalLoginBlockedTest(TestCase):
    """local_login=False. Each test creates a new client so the middleware chain
    is rebuilt with the overridden configuration."""

    @classmethod
    def setUpTestData(cls):
        cls.admin = User.objects.create_superuser(**CREDS)
        cls.token = Token(user=cls.admin, version=TokenVersionChoices.V1)
        cls.token.save()
        cls.token_header = cls.token.get_auth_header_prefix() + cls.token.token

    def setUp(self):
        self.override = override_settings(PLUGINS_CONFIG=OFF)
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.client = Client()

    def test_post_login_with_valid_password_forbidden(self):
        with self.assertLogs("netbox_sso_redirect", "WARNING"):
            r = self.client.post("/login/", CREDS)
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)
        self.assertIn("no-store", r["Cache-Control"])

    def test_post_login_with_local_param_forbidden(self):
        with self.assertLogs("netbox_sso_redirect", "WARNING"):
            r = self.client.post("/login/?local=1", CREDS)
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_method_override_does_not_bypass_block(self):
        for path in ("/login/", reverse("users-api:token_provision")):
            with self.subTest(path=path), self.assertLogs("netbox_sso_redirect", "WARNING"):
                response = self.client.post(
                    path, {**CREDS, "_method": "GET"},
                    headers={"X-HTTP-Method-Override": "GET"},
                )
            self.assertEqual(response.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    def test_other_methods_do_not_authenticate_or_issue_tokens(self):
        before = Token.objects.count()
        for path in ("/login/", reverse("users-api:token_provision")):
            for method in ("put", "patch", "delete"):
                with self.subTest(path=path, method=method):
                    response = getattr(self.client, method)(path, CREDS, content_type="application/json")
                    self.assertEqual(response.status_code, 405)
                    self.assertNotIn("_auth_user_id", self.client.session)
        self.assertEqual(Token.objects.count(), before)

    def test_token_provision_forbidden(self):
        before = Token.objects.count()
        with self.assertLogs("netbox_sso_redirect", "WARNING"):
            r = self.client.post(
                reverse("users-api:token_provision"),
                CREDS,
                content_type="application/json",
                headers={"Accept": "application/json"},
            )
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r["Content-Type"], "application/json")
        self.assertEqual(Token.objects.count(), before)

    def test_bridge_without_local_link(self):
        r = self.client.get("/login/?next=/dcim/")
        self.assertTemplateUsed(r, BRIDGE)
        self.assertNotContains(r, "Local login")
        self.assertNotContains(r, "local=1")
        self.assertContains(r, 'data-autostart="true"')

    def test_local_1_shows_bridge_without_autostart(self):
        r = self.client.get("/login/?local=1&next=/dcim/")
        self.assertTemplateUsed(r, BRIDGE)
        self.assertNotContains(r, 'name="password"')
        self.assertContains(r, 'data-autostart="false"')
        self.assertContains(r, 'name="next" value="/dcim/"')

    def test_post_login_under_script_name_forbidden(self):
        # WSGI mount: request.path = /mount/login/; Django routes using path_info /login/.
        with self.assertLogs("netbox_sso_redirect", "WARNING"):
            r = self.client.post("/login/", CREDS, SCRIPT_NAME="/mount")
        self.assertEqual(r.status_code, 403)
        self.assertNotIn("_auth_user_id", self.client.session)

    # oidc_config is decorated with @cache, so patch return_value instead of replacing the function.
    @mock.patch.object(OpenIdConnectAuth, "oidc_config", return_value=IDP)
    def test_sso_begin_still_works(self, _mock):
        r = self.client.get("/login/")
        csrf = r.cookies["csrftoken"].value
        csrf_client = Client(enforce_csrf_checks=True)
        csrf_client.cookies["csrftoken"] = csrf
        r = csrf_client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"csrfmiddlewaretoken": csrf, "next": "/"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["url"].startswith("https://idp.example/authorize"))

    def test_api_token_still_works(self):
        r = self.client.get(
            "/api/dcim/sites/",
            headers={"Authorization": self.token_header, "Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 200)

    def test_logged_in_session_unaffected(self):
        self.client.force_login(self.admin)
        self.assertEqual(self.client.get("/dcim/sites/").status_code, 200)


class LocalLoginConfigTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        User.objects.create_superuser(**CREDS)

    def test_non_bool_blocks(self):
        cfg = {"netbox_sso_redirect": {"local_login": "true"}}
        with override_settings(PLUGINS_CONFIG=cfg):
            with self.assertLogs("netbox_sso_redirect", "WARNING") as logs:
                r = Client().post("/login/", CREDS)
        self.assertEqual(r.status_code, 403)
        self.assertTrue(any("local_login" in line for line in logs.output))

    def test_invalid_backend_keeps_block(self):
        cfg = {"netbox_sso_redirect": {"backend": "nope", "local_login": False}}
        with override_settings(PLUGINS_CONFIG=cfg):
            with self.assertLogs("netbox_sso_redirect", "WARNING"):
                client = Client()
                r = client.get("/login/")
                # Redirect disabled: NetBox's page passes through, but POST remains blocked.
                self.assertTemplateUsed(r, "login.html")
                self.assertTemplateNotUsed(r, BRIDGE)
                self.assertEqual(client.post("/login/", CREDS).status_code, 403)

    def test_invalid_backend_with_local_login_unused(self):
        cfg = {"netbox_sso_redirect": {"backend": "nope", "local_login": True}}
        with override_settings(PLUGINS_CONFIG=cfg):
            with self.assertLogs("netbox_sso_redirect", "WARNING"), self.assertRaises(
                MiddlewareNotUsed
            ):
                SSORedirectMiddleware(lambda r: HttpResponse())

    def test_explicit_true_allows_post(self):
        cfg = {"netbox_sso_redirect": {"local_login": True}}
        with override_settings(PLUGINS_CONFIG=cfg):
            client = Client()
            r = client.post("/login/", CREDS)
        self.assertEqual(r.status_code, 302)
        self.assertIn("_auth_user_id", client.session)
