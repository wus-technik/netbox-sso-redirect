import re
from unittest import mock

from django.test import Client, TestCase, override_settings
from django.urls import reverse
from social_core.backends.open_id_connect import OpenIdConnectAuth

from netbox_sso_redirect.conf import get_idp_origin

BRIDGE = "netbox_sso_redirect/bridge.html"
IDP = {"authorization_endpoint": "https://idp.example/authorize"}
ERROR_URL = "/login/?local=1"  # as in the image: LOGIN_URL + "?local=1"
FAILED = "Single sign-on failed"
UNABLE = "Unable to begin single sign-on"


def plugin_cfg(local_login):
    return {"netbox_sso_redirect": {"backend": "oidc", "local_param": "local", "local_login": local_login}}


@override_settings(SOCIAL_AUTH_LOGIN_ERROR_URL=ERROR_URL)
@mock.patch.object(OpenIdConnectAuth, "oidc_config", return_value=IDP)
class SSOErrorFlowTest(TestCase):
    """Cancellation at authentik: callback with error=access_denied.

    social-core evaluates error before state; state is included here for completeness.
    Exercise the real path: complete view, AuthCanceled,
    SocialAuthExceptionMiddleware, SOCIAL_AUTH_LOGIN_ERROR_URL, and restoration of next.
    """

    def _cancelled_login(self, client, next_url="/dcim/devices/"):
        bridge = client.get(f"/login/?next={next_url}")
        token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', bridge.content.decode())[1]
        begin = client.post(
            reverse("social_auth_begin", args=["oidc"]),
            {"csrfmiddlewaretoken": token, "next": next_url},
            headers={"Accept": "application/json"},
        )
        self.assertEqual(begin.status_code, 200)
        state = client.session["oidc_state"]
        return client.get(f"/oauth/complete/oidc/?error=access_denied&state={state}")

    def _follow(self, client, response):
        hops = []
        while response.status_code == 302:
            hops.append(response["Location"])
            response = client.get(response["Location"])
        return hops, response

    def test_next_survives_cancel_with_local_login(self, _mock):
        with override_settings(PLUGINS_CONFIG=plugin_cfg(True)):
            client = Client(enforce_csrf_checks=True)
            hops, page = self._follow(client, self._cancelled_login(client))
        self.assertEqual(hops, [ERROR_URL, "/login/?local=1&next=%2Fdcim%2Fdevices%2F"])
        self.assertTemplateUsed(page, "login.html")
        self.assertContains(page, 'name="next" value="/dcim/devices/"')
        self.assertContains(page, FAILED, count=1)

    def test_next_survives_cancel_with_blocked_local_login(self, _mock):
        with override_settings(PLUGINS_CONFIG=plugin_cfg(False)):
            client = Client(enforce_csrf_checks=True)
            hops, page = self._follow(client, self._cancelled_login(client))
        self.assertEqual(hops, [ERROR_URL, "/login/?local=1&next=%2Fdcim%2Fdevices%2F"])
        self.assertTemplateUsed(page, BRIDGE)
        self.assertContains(page, 'data-autostart="false"')
        self.assertContains(page, 'name="next" value="/dcim/devices/"')
        # Exactly one message; NetBox's hidden startup hint from login.html is absent.
        self.assertContains(page, FAILED, count=1)
        self.assertNotContains(page, UNABLE)


class RestoreNextTest(TestCase):
    def _session_next(self, client, value):
        session = client.session
        session["next"] = value
        session.save()

    def test_explicit_next_wins(self):
        self._session_next(self.client, "/ipam/")
        r = self.client.get("/login/?local=1&next=/dcim/")
        self.assertEqual(r.status_code, 200)

    def test_without_session_next_no_redirect(self):
        self.assertEqual(self.client.get("/login/?local=1").status_code, 200)

    def test_unsafe_session_next_ignored(self):
        for value in ("//evil.example/", "https://evil.example/", "/\\evil.example"):
            with self.subTest(value=value):
                self._session_next(self.client, value)
                self.assertEqual(self.client.get("/login/?local=1").status_code, 200)

    def test_only_with_local_param(self):
        self._session_next(self.client, "/ipam/")
        r = self.client.get("/login/")
        self.assertEqual(r.status_code, 200)
        self.assertTemplateUsed(r, BRIDGE)

    def test_non_string_session_next_ignored(self):
        for value in (None, 42, ["/ipam/"], {"url": "/ipam/"}):
            with self.subTest(value=value):
                self._session_next(self.client, value)
                self.assertEqual(self.client.get("/login/?local=1").status_code, 200)

    def test_https_session_next_cannot_downgrade(self):
        self._session_next(self.client, "http://testserver/ipam/")
        self.assertEqual(self.client.get("/login/?local=1", secure=True).status_code, 200)

    def test_htmx_not_redirected(self):
        self._session_next(self.client, "/ipam/")
        r = self.client.get("/login/?local=1", headers={"HX-Request": "true"})
        self.assertNotEqual(r.status_code, 302)

    def test_redirect_is_not_cached(self):
        self._session_next(self.client, "/ipam/")
        r = self.client.get("/login/?local=1")
        self.assertEqual(r.status_code, 302)
        self.assertEqual(r["Location"], "/login/?local=1&next=%2Fipam%2F")
        self.assertIn("no-store", r["Cache-Control"])


class PreconnectTest(TestCase):
    def test_origin_from_oidc_endpoint(self):
        with override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT="https://sso.example.com/application/o/netbox/"):
            self.assertEqual(get_idp_origin("oidc"), "https://sso.example.com")

    def test_hyphenated_backend_name(self):
        with override_settings(SOCIAL_AUTH_MY_IDP_OIDC_ENDPOINT="https://idp.example:8443/x"):
            self.assertEqual(get_idp_origin("my-idp"), "https://idp.example:8443")

    def test_missing_or_invalid_endpoint(self):
        self.assertIsNone(get_idp_origin("azuread-oauth2"))
        for value in ("javascript:alert(1)", "/relative", "", None, 42, "https://[idp.example/x", "https://idp.example:99999/"):
            with self.subTest(value=value), override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT=value):
                self.assertIsNone(get_idp_origin("oidc"))

    def test_userinfo_not_in_origin(self):
        with override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT="https://user:pw@idp.example:8443/x"):
            self.assertEqual(get_idp_origin("oidc"), "https://idp.example:8443")

    def test_ipv6_origin(self):
        with override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT="https://[2001:db8::1]:8443/x"):
            self.assertEqual(get_idp_origin("oidc"), "https://[2001:db8::1]:8443")

    def test_malformed_endpoint_keeps_bridge(self):
        with override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT="https://[idp.example/x"):
            r = Client().get("/login/")
        self.assertEqual(r.status_code, 200)
        self.assertNotContains(r, 'rel="preconnect"')

    def test_bridge_has_preconnect(self):
        with override_settings(SOCIAL_AUTH_OIDC_OIDC_ENDPOINT="https://sso.example.com/application/o/netbox/"):
            r = Client().get("/login/")
        self.assertContains(r, '<link rel="preconnect" href="https://sso.example.com">')
        self.assertContains(r, '<link rel="dns-prefetch" href="https://sso.example.com">')

    def test_status_hidden_without_autostart(self):
        with override_settings(PLUGINS_CONFIG=plugin_cfg(False)):
            r = Client().get("/login/?local=1")
        self.assertRegex(r.content.decode(), r'id="sso-redirect-status"[^>]*\shidden>')
