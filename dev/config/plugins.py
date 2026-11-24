import os

# Test environment only. netbox-docker does not read BASE_PATH from the environment; $TEST_BP supplies -e BASE_PATH=netbox/.
BASE_PATH = os.environ.get("BASE_PATH", "")

PLUGINS = ["netbox_sso_redirect"]
# Test environment only: -e SSO_LOCAL_LOGIN=false blocks local login.
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
# As in the image: SSO errors must return to a page without auto-start to prevent a loop.
SOCIAL_AUTH_LOGIN_ERROR_URL = f"/{BASE_PATH}login/?local=1"
