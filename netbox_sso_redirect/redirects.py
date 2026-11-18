from django.conf import settings
from django.utils.http import url_has_allowed_host_and_scheme


def safe_next(request):
    """Return the last ``next`` GET value if it is a safe redirect target.

    Falls back to ``settings.LOGIN_REDIRECT_URL`` when ``next`` is missing,
    empty or points to a foreign host or a downgraded scheme.
    """
    values = request.GET.getlist("next")
    value = values[-1] if values else ""
    if value and url_has_allowed_host_and_scheme(
        value, {request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return settings.LOGIN_REDIRECT_URL
