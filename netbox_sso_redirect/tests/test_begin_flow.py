import re
from unittest import mock

from django.contrib.staticfiles import finders
from django.test import Client, TestCase
from django.urls import reverse
from social_core.backends.open_id_connect import OpenIdConnectAuth

IDP = {"authorization_endpoint": "https://idp.example/authorize"}


class BeginFlowTest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    # oidc_config ist per @cache dekoriert, daher return_value statt Funktionsersatz.
    @mock.patch.object(OpenIdConnectAuth, "oidc_config", return_value=IDP)
    def _begin(self, _mock, next_url="/dcim/devices/"):
        bridge = self.client.get(f"/login/?next={next_url}")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', bridge.content.decode())[1]
        return self.client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"csrfmiddlewaretoken": token, "next": next_url},
            headers={"Accept": "application/json"},
        )

    def test_begin_returns_idp_url_as_json(self):
        r = self._begin()
        self.assertEqual(r.status_code, 200)
        self.assertTrue(r.json()["url"].startswith("https://idp.example/authorize"))

    def test_begin_stores_next_in_session(self):
        self._begin()
        self.assertEqual(self.client.session["next"], "/dcim/devices/")

    def test_begin_without_token_is_rejected(self):
        r = self.client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"next": "/"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 403)

    def test_script_is_collectable(self):
        self.assertIsNotNone(finders.find("netbox_sso_redirect/sso-redirect.js"))
