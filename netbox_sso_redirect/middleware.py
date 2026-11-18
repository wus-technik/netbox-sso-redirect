"""Middleware: Ein anonymer GET auf LOGIN_URL liefert die SSO-Brückenseite."""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from .conf import get_settings, validate_settings
from .redirects import safe_next

logger = logging.getLogger("netbox_sso_redirect")

TEMPLATE = "netbox_sso_redirect/bridge.html"


class SSORedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.backend, self.local_param = get_settings()
        errors = validate_settings(self.backend, self.local_param, settings.AUTHENTICATION_BACKENDS)
        if errors:
            for error in errors:
                logger.warning("SSO-Weiterleitung deaktiviert: %s", error)
            raise MiddlewareNotUsed

    def _applies(self, request):
        return (
            request.method == "GET"
            and request.path == settings.LOGIN_URL
            and not request.user.is_authenticated
            and request.GET.get(self.local_param) != "1"
        )

    def __call__(self, request):
        if not self._applies(request):
            return self.get_response(request)

        if request.headers.get("HX-Request"):
            # HTMX würde die Brückenseite als Fragment einsetzen; stattdessen volle Navigation.
            response = HttpResponse()
            response["HX-Redirect"] = request.get_full_path()
            add_never_cache_headers(response)
            return response

        next_url = safe_next(request)
        query = urlencode({self.local_param: "1", "next": next_url})
        context = {
            "begin_url": reverse("social_auth_begin", args=[self.backend]),
            "next_url": next_url,
            "local_url": f"{settings.LOGIN_URL}?{query}",
        }
        response = render(request, TEMPLATE, context)
        add_never_cache_headers(response)
        response["X-Frame-Options"] = "DENY"
        return response
