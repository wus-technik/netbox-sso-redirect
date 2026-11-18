"""Einstellungen des Plugins lesen und prüfen."""

from urllib.parse import urlsplit

from django.conf import settings
from netbox.plugins import get_plugin_config
from social_core.backends.base import BaseAuth
from social_core.utils import module_member

PLUGIN_NAME = "netbox_sso_redirect"


def get_settings():
    """Liefert (backend, local_param).

    Die Standardwerte stehen explizit im Aufruf: NetBox mischt default_settings
    nur einmal beim Import der Settings ein, ein override_settings verliert sie.
    """
    backend = get_plugin_config(PLUGIN_NAME, "backend", "oidc")
    local_param = get_plugin_config(PLUGIN_NAME, "local_param", "local")
    return backend, local_param


def _social_backend_names(authentication_backends):
    """Namen aller social-core-Backends aus AUTHENTICATION_BACKENDS.

    Bewusst ohne social_core.backends.utils.load_backends, damit dessen
    globaler Cache unberührt bleibt.
    """
    names = set()
    for path in authentication_backends:
        try:
            cls = module_member(path)
        except (ImportError, AttributeError, ValueError):
            continue
        if isinstance(cls, type) and issubclass(cls, BaseAuth):
            names.add(cls.name)
    return names


def validate_settings(backend, local_param, authentication_backends):
    """Prüft die Einstellungen; leere Liste = gültig, sonst deutsche Fehlermeldungen."""
    errors = []
    if not isinstance(backend, str) or not backend.strip():
        errors.append("Die Einstellung 'backend' darf nicht leer sein.")
    if not isinstance(local_param, str) or not local_param.strip():
        errors.append("Die Einstellung 'local_param' darf nicht leer sein.")
    elif local_param == "next":
        errors.append("Die Einstellung 'local_param' darf nicht 'next' lauten.")
    if isinstance(backend, str) and backend.strip():
        if backend not in _social_backend_names(authentication_backends):
            errors.append(
                f"Das Backend '{backend}' ist in AUTHENTICATION_BACKENDS nicht als "
                "social-auth-Backend konfiguriert."
            )
    return errors


def get_local_login():
    """Liefert (erlaubt, fehler) für den lokalen Login mit Passwort.

    Nur das Bool True erlaubt ihn. Jeder andere Wert sperrt, auch ein Tippfehler wie der
    String "true": Die Sperre ist eine Sicherheitsgrenze und fällt deshalb nicht offen aus.
    """
    value = get_plugin_config(PLUGIN_NAME, "local_login", True)
    if isinstance(value, bool):
        return value, None
    return False, (
        f"Die Einstellung 'local_login' muss True oder False sein, nicht {value!r}; "
        "der lokale Login bleibt gesperrt."
    )


def get_idp_origin(backend):
    """Ursprung (Schema + Host) des IdP aus SOCIAL_AUTH_<BACKEND>_OIDC_ENDPOINT, sonst None.

    Dient nur dem Preconnect auf der Brückenseite; ohne passende Einstellung entfällt er.
    """
    name = f"SOCIAL_AUTH_{backend.upper().replace('-', '_')}_OIDC_ENDPOINT"
    endpoint = getattr(settings, name, "")
    if not isinstance(endpoint, str):
        return None
    # Ein Tippfehler in der Einstellung darf die Login-Seite nicht mit 500 lahmlegen.
    try:
        parts = urlsplit(endpoint)
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    # Aus Host und Port gebaut, nicht aus netloc: Zugangsdaten (user:pw@) gehören nicht ins HTML.
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")
