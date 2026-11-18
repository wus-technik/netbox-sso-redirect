import social_core.backends.utils
from django.test import TestCase, override_settings

from netbox_sso_redirect.conf import get_local_login, get_settings, validate_settings

OIDC = [
    "social_core.backends.open_id_connect.OpenIdConnectAuth",
    "netbox.authentication.ObjectPermissionBackend",
]


class ConfTest(TestCase):
    def test_defaults_are_valid(self):
        self.assertEqual(validate_settings("oidc", "local", OIDC), [])

    def test_empty_backend(self):
        self.assertTrue(validate_settings("", "local", OIDC))

    def test_empty_local_param(self):
        self.assertTrue(validate_settings("oidc", "", OIDC))

    def test_local_param_next_rejected(self):
        self.assertTrue(validate_settings("oidc", "next", OIDC))

    def test_backend_not_configured(self):
        self.assertTrue(validate_settings("azuread-oauth2", "local", OIDC))

    def test_non_social_backends_ignored(self):
        self.assertTrue(validate_settings("oidc", "local", OIDC[1:]))

    def test_backend_cache_untouched(self):
        before = social_core.backends.utils.BACKENDSCACHE
        validate_settings("azuread-oauth2", "local", OIDC)
        self.assertIs(social_core.backends.utils.BACKENDSCACHE, before)

    def test_get_settings_defaults(self):
        self.assertEqual(get_settings(), ("oidc", "local"))

    @override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": {"backend": "oidc"}})
    def test_get_settings_partial_config(self):
        self.assertEqual(get_settings(), ("oidc", "local"))

    def test_local_login_default_allowed(self):
        self.assertEqual(get_local_login(), (True, None))

    @override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": {"local_login": False}})
    def test_local_login_false(self):
        self.assertEqual(get_local_login(), (False, None))

    def test_local_login_non_bool_blocks(self):
        for value in ("true", "False", 1, 0, None):
            with self.subTest(value=value), override_settings(
                PLUGINS_CONFIG={"netbox_sso_redirect": {"local_login": value}}
            ):
                allowed, error = get_local_login()
                self.assertFalse(allowed)
                self.assertIn("local_login", error)
