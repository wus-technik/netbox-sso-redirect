from django.conf import settings
from django.test import RequestFactory, SimpleTestCase

from netbox_sso_redirect.redirects import safe_next

FALLBACK = settings.LOGIN_REDIRECT_URL


def _request(query, secure=False):
    """Build a request with the raw query string, so the encoding stays exact."""
    request = RequestFactory().get("/login/")
    request.META["QUERY_STRING"] = query
    if secure:
        request.META["wsgi.url_scheme"] = "https"
    return request


class SafeNextTest(SimpleTestCase):
    def test_relative_path_kept(self):
        self.assertEqual(safe_next(_request("next=/dcim/devices/")), "/dcim/devices/")

    def test_same_host_absolute_kept(self):
        self.assertEqual(
            safe_next(_request("next=http://testserver/ipam/")),
            "http://testserver/ipam/",
        )

    def test_missing_next(self):
        self.assertEqual(safe_next(_request("")), FALLBACK)

    def test_empty_next(self):
        self.assertEqual(safe_next(_request("next=")), FALLBACK)

    def test_protocol_relative(self):
        self.assertEqual(safe_next(_request("next=//evil.example/")), FALLBACK)

    def test_backslash(self):
        self.assertEqual(safe_next(_request("next=/\evil.example/")), FALLBACK)

    def test_encoded_slashes(self):
        self.assertEqual(safe_next(_request("next=%2F%2Fevil.example%2F")), FALLBACK)

    def test_double_encoded_stays_relative(self):
        self.assertEqual(
            safe_next(_request("next=%252F%252Fevil.example")), "%2F%2Fevil.example"
        )

    def test_foreign_host(self):
        self.assertEqual(safe_next(_request("next=https://evil.example/")), FALLBACK)

    def test_http_under_https(self):
        self.assertEqual(
            safe_next(_request("next=http://testserver/", secure=True)), FALLBACK
        )

    def test_repeated_next_uses_last(self):
        self.assertEqual(safe_next(_request("next=//evil&next=/ipam/")), "/ipam/")

    def test_repeated_next_last_checked(self):
        self.assertEqual(safe_next(_request("next=/ipam/&next=//evil")), FALLBACK)
