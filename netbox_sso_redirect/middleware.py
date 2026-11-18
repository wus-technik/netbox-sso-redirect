"""Middleware: SSO-Brückenseite auf LOGIN_URL und optionale Sperre des lokalen Logins."""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse, HttpResponseForbidden, JsonResponse
from django.shortcuts import render
from django.urls import reverse
from django.utils.cache import add_never_cache_headers

from .conf import get_local_login, get_settings, validate_settings
from .redirects import safe_next

logger = logging.getLogger("netbox_sso_redirect")

TEMPLATE = "netbox_sso_redirect/bridge.html"
BLOCKED_MESSAGE = "Die lokale Anmeldung ist deaktiviert. Bitte über SSO anmelden."


class SSORedirectMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response
        self.backend, self.local_param = get_settings()
        errors = validate_settings(self.backend, self.local_param, settings.AUTHENTICATION_BACKENDS)
        for error in errors:
            logger.warning("SSO-Weiterleitung deaktiviert: %s", error)
        self.redirect_enabled = not errors

        self.local_login, local_error = get_local_login()
        if local_error:
            logger.warning("%s", local_error)
        if not self.local_login:
            logger.info("Lokale Anmeldung mit Passwort ist gesperrt (local_login).")

        if not self.redirect_enabled and self.local_login:
            raise MiddlewareNotUsed

    def _blocks_password_login(self, request):
        """POST auf die beiden Wege, die NetBox Benutzername und Passwort prüfen lässt."""
        return (
            not self.local_login
            and request.method == "POST"
            and request.path in (settings.LOGIN_URL, reverse("users-api:token_provision"))
        )

    def _shows_bridge(self, request):
        if not (
            self.redirect_enabled
            and request.method == "GET"
            and request.path == settings.LOGIN_URL
            and not request.user.is_authenticated
        ):
            return False
        # Mit gesperrtem lokalem Login gibt es kein Formular mehr, auch nicht mit local=1.
        return not self.local_login or request.GET.get(self.local_param) != "1"

    def __call__(self, request):
        if self._blocks_password_login(request):
            return self._blocked_response(request)
        if not self._shows_bridge(request):
            return self.get_response(request)

        if request.headers.get("HX-Request"):
            # HTMX würde die Brückenseite als Fragment einsetzen; stattdessen volle Navigation.
            response = HttpResponse()
            response["HX-Redirect"] = request.get_full_path()
            add_never_cache_headers(response)
            return response

        next_url = safe_next(request)
        local_url = None
        if self.local_login:
            query = urlencode({self.local_param: "1", "next": next_url})
            local_url = f"{settings.LOGIN_URL}?{query}"
        context = {
            "begin_url": reverse("social_auth_begin", args=[self.backend]),
            "next_url": next_url,
            "local_url": local_url,
            # local=1 ist auch das Ziel nach einem SSO-Fehler (SOCIAL_AUTH_LOGIN_ERROR_URL);
            # ohne lokalen Login darf dort kein Autostart laufen, sonst entsteht eine Schleife.
            "autostart": request.GET.get(self.local_param) != "1",
        }
        response = render(request, TEMPLATE, context)
        add_never_cache_headers(response)
        response["X-Frame-Options"] = "DENY"
        return response

    def _blocked_response(self, request):
        logger.warning(
            "Lokale Anmeldung abgewiesen: %s %s von %s",
            request.method,
            request.path,
            request.META.get("REMOTE_ADDR"),
        )
        if request.path == settings.LOGIN_URL:
            response = HttpResponseForbidden(BLOCKED_MESSAGE, content_type="text/plain; charset=utf-8")
        else:
            response = JsonResponse({"detail": BLOCKED_MESSAGE}, status=403)
        add_never_cache_headers(response)
        return response
