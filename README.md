# netbox-sso-redirect

NetBox plugin by W&S Technik: an unauthenticated visit starts SSO immediately
(OIDC against authentik). The local login form is available only at `/login/?local=1`,
providing emergency access for the local `admin` account. With `local_login = False`,
password login is blocked entirely and can be re-enabled through configuration in an emergency.

Jira: [ITSYS-422](https://wus-technik.atlassian.net/browse/ITSYS-422) · Integrated into
`wus-technik/docker-netbox-wus` (stack 712 `netbox`, docker106).

## Status

Security review before 1.0.0: [findings and release prerequisites](docs/superpowers/reviews/2026-11-24-security-1.0.0.md).
The review found no confirmed authentication bypass in the plugin.
OIDC and Django security issues in the pinned test image remain open before full-stack approval.

Version 1.0.0 is the first stable plugin release for NetBox 4.7, with English documentation,
UI and log messages, expanded security regression coverage, and localhost-only development ports.
See the [1.0.0 release notes](docs/releases/1.0.0.md) for validation and image security prerequisites.

The implementation is tested: middleware, bridge page, `next` and settings validation,
and the local login block. Version 0.2.0 introduced `local_login` (default `True`, preserving
0.1.0 behavior). Version 0.3.0 preserves `next` after an SSO error, preconnects to the IdP,
and keeps the spinner visible until navigation (item 9), with no new settings.
The plugin ships a template and a static file (`sso-redirect.js`).
The image must run `collectstatic` after installing the plugin; otherwise the bridge script is missing.

## Where versions are defined

| Component | Source of the version |
|---|---|
| Plugin | `netbox_sso_redirect/__init__.py`: `__version__ = "1.0.0"`. `pyproject.toml` reads this attribute for package metadata. |
| Supported NetBox range | `min_version = "4.7.0"` and `max_version = "4.7.99"` in the plugin config. These are compatibility limits, not installation pins. |
| Local NetBox test image | `dev/docker-compose.yml`: `netboxcommunity/netbox@sha256:22cf3c61fc367fb74a5cf6de018e9d7e10a7da8d09a695eab30740793040de08` (v4.7.3). |
| Django and social-auth | NetBox's upstream [v4.7.3 requirements.txt](https://github.com/netbox-community/netbox/blob/v4.7.3/requirements.txt) pins `Django==6.1.2`, `social-auth-core==5.2.0`, and `social-auth-app-django==6.1.0`. They are already installed in the test image. |
| Smoke-test expectations | `tests/test_smoke.py` asserts NetBox 4.7.3 and social-auth-core 5.2.0. Assertions verify the selected image; they do not install or pin dependencies. |
| Production image and plugin revision | Managed in `docker-netbox-wus`; the plugin revision is pinned in its `plugin_requirements.txt`. Its current dependency overrides were not inspected in this review. |

Updating these runtime dependencies is an image/NetBox task. This plugin's `pyproject.toml`
does not override them. When selecting a patched test image, update its digest and the
smoke-test expectations together, then rerun the tests.

## Why a plugin

NetBox 4.7 does not provide this behavior (verified against a running 4.7.3 container on 2026-11-18):

- `LOGIN_FORM_HIDDEN = True` only hides the form in the template. `LoginView.post()` does
  not check this setting; posting a username and password to `/login/` still works.
- There is no automatic redirect.
- Since social-auth-app-django 6, SSO starts with a **POST and CSRF token** to
  `/oauth/begin/<backend>/` (NetBox's `SocialAuthBeginView`, URL name `social_auth_begin`).
  The social-django route `/oauth/login/<backend>/` (`social:begin`) also returns 405 on GET.
  A simple reverse-proxy redirect is therefore insufficient.
- An overridden `templates/login.html` would need comparison with the original on every
  NetBox upgrade. Middleware does not depend on that template.

## Intended behavior

1. **Middleware**, registered through `PluginConfig.middleware`, runs after
   `AuthenticationMiddleware` and `CsrfViewMiddleware`. An anonymous **GET** to
   `settings.LOGIN_URL` (compared with `request.path`, including `BASE_PATH`) renders
   a bridge page unless the query parameter is exactly `local=1`. Authenticated users,
   HEAD, POST, and other paths pass through to NetBox, subject to the password block in
   item 8. HTMX requests (`HX-Request` header) receive an empty response with
   `HX-Redirect` pointing to the same URL, forcing full navigation instead of inserting a fragment.
2. **Bridge page:** a form contains the CSRF token from `get_token(request)` (the cookie
   is `HttpOnly`) and `next` as an HTML-escaped hidden POST field. Its action is
   `reverse('social_auth_begin', args=[backend])`, NetBox's wrapper rather than `social:begin`.
   Like NetBox's `initSSOForms()`, the script submits it using `fetch` with
   `Accept: application/json` and follows the returned `url` via `location.assign()`.
   Chromium checks CSP `form-action` at every redirect hop, so a native form POST could
   fail silently. Without JavaScript, the form and submit button remain available.
   The script is a static plugin file, not inline.
   Response headers include `Cache-Control: no-store, private` and `X-Frame-Options: DENY`.
   Like NetBox's `login.html`, the bridge extends `base/base.html` for the logo, color mode,
   `BANNER_LOGIN`, and messages. Its script URL includes `?v=<version>` to invalidate
   old browser caches after an update. The form deliberately omits the `sso-login-form`
   class so NetBox's `initSSOForms()` does not attach a second handler.
3. **Validate `next`:** use
   `url_has_allowed_host_and_scheme(next, {request.get_host()}, require_https=request.is_secure())`.
   Invalid or missing values fall back to `settings.LOGIN_REDIRECT_URL`.
   Other query parameters are not forwarded to the SSO form.
4. **`/login/?local=1`** renders the normal NetBox login form. This requires
   `LOGIN_FORM_HIDDEN = False` (the default).
5. **POST to `/login/`** is unchanged when `local_login = True`, even without `local=1`.
   The query parameter prevents accidental visits to the form; it is not a security boundary.
   That boundary is `local_login = False` (item 8).
6. **Unaffected:** token-based API access, `/oauth/*`, static files, and other paths.
   Exception when `local_login = False`: `POST /api/users/tokens/provision/` (item 8).
7. **Settings** in `PLUGINS_CONFIG['netbox_sso_redirect']`: `backend` (default `oidc`),
   `local_param` (default `local`), and `local_login` (default `True`).
   Startup validation requires non-empty `backend` and `local_param`,
   rejects `local_param = "next"`, and checks that the backend is configured in
   `AUTHENTICATION_BACKENDS` / `REMOTE_AUTH_BACKEND`.
   Invalid configuration disables redirection and logs a warning; the normal login page
   remains available. An active password block remains enforced (item 8).
8. **`local_login = False` blocks password login.** NetBox 4.7.3's standard configuration
   has two anonymous username/password entry points: `LoginView` (URL name `login`)
   and `POST /api/users/tokens/provision/`, which issues an API token from credentials.
   The middleware resolves the path (`resolve(request.path_info)`) and returns 403 for
   every POST to either view (text or JSON, logging the path and client address),
   regardless of `local=1` or authentication status.
   `?local=1` then shows the bridge without auto-start or a "Local login" link.
   SSO errors also lead here (`SOCIAL_AUTH_LOGIN_ERROR_URL`); auto-start would create a loop.
   The bridge displays social-auth messages. SSO, existing API tokens, and sessions continue
   to work. Only the boolean `True` permits local login; every other value, including
   the string `"true"`, blocks it and logs a warning.
   Additional password entry points (Django admin, Basic Auth, other backends) are outside
   this block's scope. **Emergency access:** if authentik is unavailable, set
   `local_login` to `True`, restart NetBox, sign in with the emergency account at
   `/login/?local=1`, then restore the block.
9. **SSO error recovery and waiting behavior** (since 0.3.0):
   - **Preserve `next`.** social-core stores it in the session when login starts, but redirects
     to the fixed `SOCIAL_AUTH_LOGIN_ERROR_URL` without it on error. An anonymous GET to
     `LOGIN_URL?local=1` without `next` is redirected once to the same URL with the safe
     session value (302, `no-store`). An explicit query value takes precedence; HTMX requests
     are not redirected. This works in both local-login modes without image changes.
     social-core replaces the session value only when a new start supplies `next`,
     so an older value may remain. It still passes item 3's validation; at worst,
     the user lands on another page on the same host.
   - **One message.** Cancelling at authentik produces one NetBox toast ("Single sign-on
     failed …"). NetBox's `login.html` also contains a hidden `#sso-error` block
     ("Unable to begin single sign-on …", `d-none`), which text extraction may include.
     With local login blocked, that extra block is absent.
   - **Preconnect:** `preconnect` and `dns-prefetch` links target the origin from
     `SOCIAL_AUTH_<BACKEND>_OIDC_ENDPOINT` (for `oidc`: `SOCIAL_AUTH_OIDC_OIDC_ENDPOINT`).
     Only HTTP/HTTPS are accepted. The origin is built from host and port, excluding
     credentials. Invalid or missing settings omit the links.
   - **Spinner until navigation**, including manual retries. Returning from the
     back-forward cache (especially iOS Safari) resets the spinner and button without auto-start.
   - No plugin inline styles or scripts; `style-src 'self'` remains possible.
     NetBox's own `base.html` inline scripts affect `script-src`.

## Image responsibilities

These settings belong in `docker-netbox-wus`:

- **Prevent login loops:** set `SOCIAL_AUTH_LOGIN_ERROR_URL` to `LOGIN_URL` plus
  `?local=1`, including `BASE_PATH`. NetBox defaults to `LOGIN_URL`; configuration
  loaded afterwards overrides it.
- Keep **`LOGIN_FORM_HIDDEN = False`**, or `?local=1` cannot show the form.
- Read **`local_login`** from a stack environment variable (blocked by default) so
  emergency access can be enabled without rebuilding. Convert it explicitly to a boolean
  in `plugins.py`.
- **Password accounts:** only the emergency account retains a usable password;
  SSO-created accounts have none.
- **Logout:** NetBox redirects to `LOGOUT_REDIRECT_URL` without performing OIDC logout.
  Point it to authentik's end-session URL. The landing page must not be `/login/`
  without `local=1`, which would immediately start SSO again. Verify end-to-end whether
  authentik ends the session without `id_token_hint`.
- **Proxy:** overwrite `X-Forwarded-Host` and `X-Forwarded-Proto` because NetBox trusts
  them. Match `ALLOWED_HOSTS` and `CSRF_TRUSTED_ORIGINS` to the public origin.
  Record the actual proxy CSP before rollout.

## Existing image integration

- `configuration/extra.py` sets `SOCIAL_AUTH_PIPELINE` with `create_user` and custom
  steps (`custom_pipeline.add_groups`, `remove_groups`, `set_roles`).
- `configuration/authentik.py` sets `SOCIAL_AUTH_OIDC_*` and `LOGOUT_REDIRECT_URL`
  from the environment (logout defaults to `/`).
- Plugins are pinned exactly in `plugin_requirements.txt` and enabled in
  `configuration/plugins.py`.

## Development

The test environment is `dev/docker-compose.yml`, using the NetBox 4.7.3 image and
digest listed above, PostgreSQL, Redis, and a dummy IdP. The plugin is mounted through
`PYTHONPATH=/opt/plugin`, not installed. Published ports bind to `127.0.0.1` because
the environment uses known development credentials and a development secret key.

Under Git Bash on Windows, run `export MSYS_NO_PATHCONV=1` first to prevent rewriting
`/opt/...` paths. Initial database setup takes several minutes.

```bash
docker compose -f dev/docker-compose.yml up -d postgres redis idp
# $TEST
docker compose -f dev/docker-compose.yml run --rm netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect --keepdb -v 2
# $TEST_BP
docker compose -f dev/docker-compose.yml run --rm -e BASE_PATH=netbox/ netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect.tests.test_base_path --keepdb -v 2
```

For a browser preview, run `docker compose -f dev/docker-compose.yml run -d --name sso-preview
--service-ports [-e SSO_LOCAL_LOGIN=false] netbox`, then run `manage.py collectstatic --no-input`
in the container. The page is at `http://localhost:8000/login/`.

Tests run against real NetBox through `manage.py test netbox_sso_redirect`. Coverage includes
the bridge and headers through the complete middleware stack; `next` variants (`//evil`,
`/\\evil`, encoded and double-encoded slashes, HTTP under HTTPS, empty and repeated values);
`local=1` and variants; `BASE_PATH`; API tokens; HTMX; HEAD; authenticated users;
invalid settings; and password blocking with valid credentials for both the form and
token provisioning, including prefixed URLs. SSO start, tokens, and existing sessions remain
available. Error-callback behavior is covered with mocked discovery; the real authentik
flow and logout still require staging checks.

Image integration pins the plugin to a **commit SHA**, using a tag only as a comment, e.g.
`git+https://github.com/wus-technik/netbox-sso-redirect@<sha>  # v0.2.0`.
The repository is public, so installation does not require a GitHub read token.
If using a private mirror, supply its read token only through a BuildKit `--secret`
mount in the same `RUN` step, never through `--build-arg` or the URL, to avoid retaining
it in image layers, logs, or pip caches.

`max_version = "4.7.99"` deliberately excludes NetBox 4.8. Test against a new NetBox
version before raising the limit. Keep `__version__` a literal because `pyproject.toml`
reads it through `attr`.
