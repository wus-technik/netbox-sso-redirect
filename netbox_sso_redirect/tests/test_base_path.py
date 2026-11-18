from unittest import skipUnless

from django.conf import settings
from django.test import TestCase

BRIDGE = "netbox_sso_redirect/bridge.html"


@skipUnless(settings.BASE_PATH == "netbox/", "nur mit $TEST_BP")
class BasePathTest(TestCase):
    def test_bridge_with_prefix(self):
        r = self.client.get("/netbox/login/")
        self.assertTemplateUsed(r, BRIDGE)
        self.assertContains(r, 'action="/netbox/oauth/begin/oidc/"')
        self.assertContains(r, "/netbox/static/netbox_sso_redirect/sso-redirect.js")
        self.assertContains(r, 'href="/netbox/login/?local=1&amp;next=%2Fnetbox%2F"')
        self.assertContains(r, 'name="next" value="/netbox/"')  # Rückfall LOGIN_REDIRECT_URL

    def test_local_with_prefix(self):
        self.assertTemplateUsed(self.client.get("/netbox/login/?local=1"), "login.html")
