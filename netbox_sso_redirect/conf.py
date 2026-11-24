"""Read and validate plugin settings."""

from urllib.parse import urlsplit

from django.conf import settings
from netbox.plugins import get_plugin_config
from social_core.backends.base import BaseAuth
from social_core.utils import module_member

PLUGIN_NAME = "netbox_sso_redirect"


def get_settings():
    """Return (backend, local_param).

    Pass defaults explicitly: NetBox merges default_settings only once when
    importing settings, so override_settings would otherwise lose them.
    """
    backend = get_plugin_config(PLUGIN_NAME, "backend", "oidc")
    local_param = get_plugin_config(PLUGIN_NAME, "local_param", "local")
    return backend, local_param


def _social_backend_names(authentication_backends):
    """Return the names of all social-core backends in AUTHENTICATION_BACKENDS.

    Avoid social_core.backends.utils.load_backends to leave its global cache
    untouched.
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
    """Validate settings; return an empty list if valid, otherwise error messages."""
    errors = []
    if not isinstance(backend, str) or not backend.strip():
        errors.append("The 'backend' setting must not be empty.")
    if not isinstance(local_param, str) or not local_param.strip():
        errors.append("The 'local_param' setting must not be empty.")
    elif local_param == "next":
        errors.append("The 'local_param' setting must not be 'next'.")
    if isinstance(backend, str) and backend.strip():
        if backend not in _social_backend_names(authentication_backends):
            errors.append(
                f"The backend '{backend}' is not configured as a social-auth backend "
                "in AUTHENTICATION_BACKENDS."
            )
    return errors


def get_local_login():
    """Return (allowed, error) for local password login.

    Only the boolean True permits login. Every other value blocks it, including a
    typo such as the string "true": this security boundary must fail closed.
    """
    value = get_plugin_config(PLUGIN_NAME, "local_login", True)
    if isinstance(value, bool):
        return value, None
    return False, (
        f"The 'local_login' setting must be True or False, not {value!r}; "
        "local login remains blocked."
    )


def get_idp_origin(backend):
    """Return the IdP origin from SOCIAL_AUTH_<BACKEND>_OIDC_ENDPOINT, or None.

    Used only for the bridge page's preconnect; omitted without a valid setting.
    """
    name = f"SOCIAL_AUTH_{backend.upper().replace('-', '_')}_OIDC_ENDPOINT"
    endpoint = getattr(settings, name, "")
    if not isinstance(endpoint, str):
        return None
    # A configuration typo must not break the login page with a 500 response.
    try:
        parts = urlsplit(endpoint)
        host, port = parts.hostname, parts.port
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not host:
        return None
    # Build from host and port, not netloc: credentials (user:pw@) must not appear in HTML.
    if ":" in host:
        host = f"[{host}]"
    return f"{parts.scheme}://{host}" + (f":{port}" if port is not None else "")
