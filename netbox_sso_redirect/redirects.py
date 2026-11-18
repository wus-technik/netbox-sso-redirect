from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def is_safe(request, value):
    """True, wenn ``value`` ein Weiterleitungsziel auf diesem Host ohne Schema-Abstieg ist."""
    return bool(value) and url_has_allowed_host_and_scheme(
        value, {request.get_host()}, require_https=request.is_secure()
    )


def session_next(request):
    """Das ``next``, das social-core beim SSO-Start in der Session abgelegt hat, falls sicher."""
    value = request.session.get("next", "")
    return value if isinstance(value, str) and is_safe(request, value) else None


def safe_next(request):
    """Return the last ``next`` GET value if it is a safe redirect target.

    Falls back to ``settings.LOGIN_REDIRECT_URL`` when ``next`` is missing,
    empty or points to a foreign host or a downgraded scheme.
    """
    values = request.GET.getlist("next")
    value = values[-1] if values else ""
    if is_safe(request, value):
        return value
    return settings.LOGIN_REDIRECT_URL
