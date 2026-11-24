import base64
import hashlib
import re
from unittest import mock
from urllib.parse import parse_qs, urlsplit

from django.contrib.staticfiles import finders
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from social_core.backends.open_id_connect import OpenIdConnectAuth

IDP = {"authorization_endpoint": "https://idp.example/authorize"}


class BeginFlowTest(TestCase):
    def setUp(self):
        self.client = Client(enforce_csrf_checks=True)

    # oidc_config is decorated with @cache, so patch return_value instead of replacing the function.
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

    @override_settings(SOCIAL_AUTH_OIDC_USE_PKCE=True)
    def test_pkce_s256_challenge_matches_session_verifier(self):
        response = self._begin()
        query = parse_qs(urlsplit(response.json()["url"]).query)
        verifier = self.client.session["oidc_code_verifier"]
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        self.assertEqual(query["code_challenge_method"], ["S256"])
        self.assertEqual(query["code_challenge"], [challenge])

    def test_begin_without_token_is_rejected(self):
        r = self.client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"next": "/"},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(r.status_code, 403)

    def test_script_is_collectable(self):
        self.assertIsNotNone(finders.find("netbox_sso_redirect/sso-redirect.js"))

    def test_foreign_origin_with_valid_csrf_token_is_rejected(self):
        bridge = self.client.get("/login/", secure=True)
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', bridge.content.decode())[1]
        response = self.client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"csrfmiddlewaretoken": token, "next": "/"},
            secure=True,
            headers={"Origin": "https://evil.example", "Accept": "application/json"},
        )
        self.assertEqual(response.status_code, 403)
        self.assertNotIn("oidc_state", self.client.session)

    def test_get_cannot_start_sso(self):
        for name in ("social_auth_begin", "social:begin"):
            with self.subTest(name=name):
                self.assertEqual(self.client.get(reverse(name, args=["oidc"])).status_code, 405)
        self.assertNotIn("oidc_state", self.client.session)
