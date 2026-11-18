import os

# Nur für die Testumgebung. netbox-docker liest BASE_PATH nicht aus der Umgebung; $TEST_BP setzt ihn per -e BASE_PATH=netbox/.
BASE_PATH = os.environ.get("BASE_PATH", "")

PLUGINS = ["netbox_sso_redirect"]
# Nur für die Testumgebung: -e SSO_LOCAL_LOGIN=false sperrt den lokalen Login.
PLUGINS_CONFIG = {
    "netbox_sso_redirect": {
        "backend": "oidc",
        "local_param": "local",
        "local_login": os.environ.get("SSO_LOCAL_LOGIN", "true") == "true",
    }
}
REMOTE_AUTH_BACKEND = "social_core.backends.open_id_connect.OpenIdConnectAuth"
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "http://idp:9000/application/o/netbox"
SOCIAL_AUTH_OIDC_KEY = "netbox-dev"
SOCIAL_AUTH_OIDC_SECRET = "netbox-dev"
# Wie im Image: Nach einem SSO-Fehler auf die Seite ohne Autostart, sonst entsteht eine Schleife.
SOCIAL_AUTH_LOGIN_ERROR_URL = f"/{BASE_PATH}login/?local=1"
