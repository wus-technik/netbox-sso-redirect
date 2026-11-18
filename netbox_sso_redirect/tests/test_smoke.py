from importlib.metadata import version

from django.apps import apps
from django.conf import settings
from django.test import TestCase


class PluginLoadedTest(TestCase):
    def test_plugin_installed(self):
        self.assertTrue(apps.is_installed("netbox_sso_redirect"))

    def test_login_url_from_netbox(self):
        self.assertEqual(settings.LOGIN_URL, "/login/")

    def test_versions(self):
        self.assertEqual(settings.RELEASE.version, "4.7.3")
        self.assertEqual(version("social-auth-core"), "5.2.0")
