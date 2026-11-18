from netbox.plugins import PluginConfig

__version__ = "0.1.0"


class NetBoxSSORedirectConfig(PluginConfig):
    name = "netbox_sso_redirect"
    verbose_name = "SSO Redirect"
    description = "Startet den SSO-Login automatisch; lokales Formular nur über /login/?local=1"
    version = __version__
    author = "W&S Technik GmbH"
    base_url = "sso-redirect"
    min_version = "4.7.0"
    max_version = "4.7.99"
    default_settings = {
        "backend": "oidc",
        "local_param": "local",
    }
    # Middleware folgt (ITSYS-422)
    middleware = []


config = NetBoxSSORedirectConfig
