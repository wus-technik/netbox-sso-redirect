"""Middleware: SSO-Brückenseite auf LOGIN_URL und optionale Sperre des lokalen Logins."""

import logging
from urllib.parse import urlencode

from django.conf import settings
from django.core.exceptions import MiddlewareNotUsed
from django.http import HttpResponse, HttpResponseForbidden, HttpResponseRedirect, JsonResponse
from django.shortcuts import render
from django.urls import Resolver404, resolve, reverse
from django.utils.cache import add_never_cache_headers

from . import __version__
from .conf import get_idp_origin, get_local_login, get_settings, validate_settings
from .redirects import safe_next, session_next

logger = logging.getLogger("netbox_sso_redirect")

TEMPLATE = "netbox_sso_redirect/bridge.html"
BLOCKED_MESSAGE = "Die lokale Anmeldung ist deaktiviert. Bitte über SSO anmelden."
# Die Views, an denen NetBox anonym Benutzername und Passwort prüft (4.7.3).
LOGIN_VIEW = "login"
PASSWORD_VIEWS = frozenset({LOGIN_VIEW, "users-api:token_provision"})


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

    @staticmethod
    def _view_name(request):
        """Name der View, auf die Django die Anfrage verteilt (path_info, ohne SCRIPT_NAME)."""
        try:
            # request.urlconf: falls eine frühere Middleware eine eigene URL-Konfiguration setzt.
            return resolve(request.path_info, urlconf=getattr(request, "urlconf", None)).view_name
        except Resolver404:
            return None

    def _blocks_password_login(self, request):
        """POST auf eine View, die Benutzername und Passwort prüft.

        Geprüft wird die aufgelöste View, nicht der Pfad: LOGIN_URL ist nur das Ziel der
        Umleitung, und request.path enthält SCRIPT_NAME, nach dem Django nicht verteilt.
        """
        return (
            not self.local_login
            and request.method == "POST"
            and self._view_name(request) in PASSWORD_VIEWS
        )

    def _is_anonymous_login_get(self, request):
        return (
            self.redirect_enabled
            and request.method == "GET"
            and request.path == settings.LOGIN_URL
            and not request.user.is_authenticated
        )

    def _restore_next(self, request):
        """Nach einem SSO-Fehler fehlt next: SOCIAL_AUTH_LOGIN_ERROR_URL ist fest /login/?local=1.

        social-core hat next beim Start in der Session abgelegt; damit wird die Fehlerseite einmal
        auf dieselbe URL mit next umgeleitet, sodass ein neuer Versuch auf der Zielseite landet.
        """
        if not (
            self._is_anonymous_login_get(request)
            and request.GET.get(self.local_param) == "1"
            and "next" not in request.GET
            and not request.headers.get("HX-Request")
        ):
            return None
        next_url = session_next(request)
        if not next_url:
            return None
        query = request.GET.copy()
        query["next"] = next_url
        response = HttpResponseRedirect(f"{settings.LOGIN_URL}?{query.urlencode()}")
        add_never_cache_headers(response)
        return response

    def _shows_bridge(self, request):
        if not self._is_anonymous_login_get(request):
            return False
        # Mit gesperrtem lokalem Login gibt es kein Formular mehr, auch nicht mit local=1.
        return not self.local_login or request.GET.get(self.local_param) != "1"

    def __call__(self, request):
        if self._blocks_password_login(request):
            return self._blocked_response(request)
        restore = self._restore_next(request)
        if restore is not None:
            return restore
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
            "plugin_version": __version__,
            "idp_origin": get_idp_origin(self.backend),
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
        if self._view_name(request) == LOGIN_VIEW:
            response = HttpResponseForbidden(BLOCKED_MESSAGE, content_type="text/plain; charset=utf-8")
        else:
            response = JsonResponse({"detail": BLOCKED_MESSAGE}, status=403)
        add_never_cache_headers(response)
        return response
