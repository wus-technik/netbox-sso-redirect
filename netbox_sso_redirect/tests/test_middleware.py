from urllib.parse import parse_qs, urlsplit

from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from users.choices import TokenVersionChoices
from users.models import Token, User

from netbox_sso_redirect.middleware import SSORedirectMiddleware

BRIDGE = "netbox_sso_redirect/bridge.html"


class SSORedirectMiddlewareTest(TestCase):
    @classmethod
    def setUpTestData(cls):
        cls.user = User.objects.create_user(username="user", password="user-pass-123")
        cls.admin = User.objects.create_superuser(username="admin", password="admin-pass-123")
        # v1-Token: Die Testumgebung setzt kein API_TOKEN_PEPPERS, v2-Tokens lassen sich
        # ohne Pepper nicht speichern. Header-Format liefert NetBox selbst.
        cls.token = Token(user=cls.admin, version=TokenVersionChoices.V1)
        cls.token.save()
        cls.token_header = cls.token.get_auth_header_prefix() + cls.token.token

    def test_anonymous_get_login_renders_bridge(self):
        r = self.client.get("/login/?next=/dcim/devices/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, BRIDGE)
        self.assertContains(r, f'action="{reverse("social_auth_begin", args=["oidc"])}"')
        self.assertContains(r, 'name="csrfmiddlewaretoken"')
        self.assertContains(r, 'name="next" value="/dcim/devices/"')
        self.assertContains(r, 'href="/login/?local=1&amp;next=%2Fdcim%2Fdevices%2F"')

    def test_bridge_headers(self):
        r = self.client.get("/login/")
        self.assertIn("no-store", r["Cache-Control"])
        self.assertIn("private", r["Cache-Control"])
        self.assertEqual(r["X-Frame-Options"], "DENY")

    def test_next_is_escaped(self):
        r = self.client.get('/login/?next=/x"><script>')
        self.assertContains(r, 'name="next" value="/x&quot;&gt;&lt;script&gt;"')
        self.assertNotContains(r, '"><script>')

    def test_local_1_shows_netbox_form(self):
        r = self.client.get("/login/?local=1")
        self.assertTemplateUsed(r, "login.html")
        self.assertContains(r, 'name="password"')

    def test_local_variants_render_bridge(self):
        for q in ("local=0", "local=", "LOCAL=1", "local=true"):
            with self.subTest(q=q):
                self.assertTemplateUsed(self.client.get(f"/login/?{q}"), BRIDGE)

    def test_authenticated_user_passes_through(self):
        self.client.force_login(self.user)
        r = self.client.get("/login/?next=/ipam/")
        self.assertTemplateNotUsed(r, BRIDGE)

    def test_head_passes_through(self):
        r = self.client.head("/login/")
        self.assertTemplateNotUsed(r, BRIDGE)
        self.assertTemplateUsed(r, "login.html")

    def test_post_login_without_local_reaches_netbox(self):
        r = self.client.post("/login/", {"username": "x", "password": "y"})
        self.assertTemplateUsed(r, "login.html")
        self.assertContains(r, 'name="password"')

    def test_htmx_on_login_gets_hx_redirect(self):
        r = self.client.get("/login/?next=/dcim/", headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["HX-Redirect"], "/login/?next=/dcim/")
        self.assertTemplateNotUsed(r, BRIDGE)

    def test_htmx_expired_session_full_navigation(self):
        r = self.client.get("/dcim/devices/", headers={"HX-Request": "true"})
        self.assertEqual(r.status_code, 302)
        hop = self.client.get(r["Location"], headers={"HX-Request": "true"})
        self.assertEqual(hop["HX-Redirect"], r["Location"])
        # Geparst vergleichen: Djangos redirect_to_login kodiert mit urlencode(safe="/"),
        # die Schrägstriche in next bleiben also unkodiert.
        self.assertEqual(parse_qs(urlsplit(hop["HX-Redirect"]).query)["next"], ["/dcim/devices/"])
        self.assertTemplateUsed(self.client.get(hop["HX-Redirect"]), BRIDGE)

    def test_other_paths_untouched(self):
        cases = {"/oauth/login/oidc/": 405, "/dcim/devices/": 302}
        for path, status in cases.items():
            with self.subTest(path=path):
                r = self.client.get(path)
                self.assertEqual(r.status_code, status)
                self.assertTemplateNotUsed(r, BRIDGE)

    def test_api_with_valid_token(self):
        r = self.client.get(
            "/api/dcim/sites/",
            headers={"Authorization": self.token_header, "Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r["Content-Type"], "application/json")

    def test_api_with_invalid_token(self):
        r = self.client.get(
            "/api/dcim/sites/",
            headers={"Authorization": "Token " + "0" * 40, "Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 403)
        self.assertTemplateNotUsed(r, BRIDGE)

    @override_settings(LOGIN_URL="/anmelden/")
    def test_login_url_read_at_runtime(self):
        self.assertTemplateUsed(self.client.get("/anmelden/"), BRIDGE)
        self.assertTemplateNotUsed(self.client.get("/login/"), BRIDGE)

    def test_invalid_settings_raise_middleware_not_used(self):
        for cfg in (
            {"backend": "nope", "local_param": "local"},
            {"backend": "oidc", "local_param": "next"},
        ):
            with self.subTest(cfg=cfg), override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": cfg}):
                with self.assertLogs("netbox_sso_redirect", "WARNING"), self.assertRaises(
                    MiddlewareNotUsed
                ):
                    SSORedirectMiddleware(lambda r: HttpResponse())

    def test_invalid_settings_full_stack_falls_back_to_netbox_login(self):
        for cfg in (
            {"backend": "nope", "local_param": "local"},
            {"backend": "oidc", "local_param": "next"},
        ):
            with self.subTest(cfg=cfg), override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": cfg}):
                with self.assertLogs("netbox_sso_redirect", "WARNING"):
                    r = Client().get("/login/")  # neuer Client = neuer Handler = neue Middleware-Kette
                self.assertEqual(r.status_code, 200)
                self.assertTemplateUsed(r, "login.html")
                self.assertTemplateNotUsed(r, BRIDGE)
