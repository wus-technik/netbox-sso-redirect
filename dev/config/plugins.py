PLUGINS = ["netbox_sso_redirect"]
PLUGINS_CONFIG = {"netbox_sso_redirect": {"backend": "oidc", "local_param": "local"}}
REMOTE_AUTH_BACKEND = "social_core.backends.open_id_connect.OpenIdConnectAuth"
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "http://idp:9000/application/o/netbox"
SOCIAL_AUTH_OIDC_KEY = "netbox-dev"
SOCIAL_AUTH_OIDC_SECRET = "netbox-dev"
