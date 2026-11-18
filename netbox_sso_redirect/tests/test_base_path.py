from unittest import skipUnless

from django.conf import settings
from django.test import Client, TestCase, override_settings
from users.models import User

BRIDGE = "netbox_sso_redirect/bridge.html"


@skipUnless(settings.BASE_PATH == "netbox/", "nur mit $TEST_BP")
class BasePathTest(TestCase):
    def test_bridge_with_prefix(self):
        r = self.client.get("/netbox/login/")
        self.assertTemplateUsed(r, BRIDGE)
        self.assertContains(r, 'action="/netbox/oauth/begin/oidc/"')
        self.assertContains(r, "/netbox/static/netbox_sso_redirect/sso-redirect.js?v=")
        self.assertContains(r, 'href="/netbox/login/?local=1&amp;next=%2Fnetbox%2F"')
        self.assertContains(r, 'name="next" value="/netbox/"')  # Rückfall LOGIN_REDIRECT_URL

    def test_local_with_prefix(self):
        self.assertTemplateUsed(self.client.get("/netbox/login/?local=1"), "login.html")

    def test_restore_next_with_prefix(self):
        session = self.client.session
        session["next"] = "/netbox/dcim/"
        session.save()
        r = self.client.get("/netbox/login/?local=1")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/netbox/login/?local=1&next=%2Fnetbox%2Fdcim%2F")

    def test_block_with_prefix(self):
        User.objects.create_user(username="u", password="u-pass-123")
        cfg = {"netbox_sso_redirect": {"local_login": False}}
        with override_settings(PLUGINS_CONFIG=cfg):
            client = Client()
            with self.assertLogs("netbox_sso_redirect", "WARNING"):
                self.assertEqual(
                    client.post("/netbox/login/", {"username": "u", "password": "u-pass-123"}).status_code,
                    403,
                )
            with self.assertLogs("netbox_sso_redirect", "WARNING"):
                r = client.post(
                    "/netbox/api/users/tokens/provision/",
                    {"username": "u", "password": "u-pass-123"},
                    content_type="application/json",
                )
            self.assertEqual(r.status_code, 403)
