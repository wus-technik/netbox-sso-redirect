# netbox-sso-redirect — implementation plan

> Historical implementation plan. The current README and code describe subsequent changes.
> The original plan required German commit messages; the repository's current documentation language is English.

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** An anonymous GET to `LOGIN_URL` immediately starts OIDC login against authentik;
the local form remains accessible through `?local=1`.

**Architecture:** Middleware registered through `PluginConfig.middleware` intercepts GET
requests to `LOGIN_URL` and renders a bridge page. The page uses `fetch` with
`Accept: application/json` to POST a CSRF token and validated `next` to NetBox's
`social_auth_begin`, then follows the returned URL. Everything else passes through to NetBox.

**Tech stack:** Python 3.12, Django as shipped in NetBox 4.7.3, social-auth-app-django 6.1.0 /
social-auth-core 5.2.0 (pinned by NetBox 4.7.3), netbox-docker on Docker Desktop,
Django's `manage.py test` runner.

**Specification:** README sections "Intended behavior", "Image responsibilities", and
"Development". Reviews: `docs/superpowers/reviews/2026-11-18-spec-readme.md` and
`docs/superpowers/reviews/2026-11-18-plan.md`. Ref: ITSYS-422.

## Global constraints

- Keep NetBox `min_version = "4.7.0"` and `max_version = "4.7.99"`.
- Keep `__version__` a string literal in `netbox_sso_redirect/__init__.py`.
- Settings in `PLUGINS_CONFIG['netbox_sso_redirect']`: `backend` (default `oidc`),
  `local_param` (default `local`).
- SSO POST destination: `reverse('social_auth_begin', args=[backend])`, never
  `social:begin` or a fixed path.
- No inline JavaScript; place the script under `static/netbox_sso_redirect/`.
- Bridge headers: `Cache-Control` includes `no-store` and `private`;
  `X-Frame-Options: DENY`.
- Invalid or missing `next` falls back to `settings.LOGIN_REDIRECT_URL`.
- No runtime dependencies beyond those provided by NetBox.
- For each commit, stage task files with `git add`, inspect `git diff --cached --stat`,
  then commit. Include `ITSYS-422` in the subject and omit AI co-author trailers.

## Review focus

1. **Session expiry during an HTMX request:** full SSO navigation, not a bridge fragment.
   Task 4 test: `test_htmx_expired_session_full_navigation`.
2. **Foreign-host `next` variants** (`//evil`, `/\evil`, `%2F%2Fevil`, HTTP under HTTPS):
   fall back to `LOGIN_REDIRECT_URL`. Task 3 tests.
3. **Misconfiguration** (invalid backend, `local_param = "next"`, partial configuration):
   normal NetBox login plus a warning, not 500 or a loop. Tasks 2 and 4.
4. **`BASE_PATH`:** prefix the begin URL, script URL, local link, and fallback destination.
   Task 4, separate `$TEST_BP` run.
5. **`local` variants** (`local=0`, `local=`, `LOCAL=1`): bridge page;
   only exact `local=1` shows the form. Task 4.

Intentionally excluded from local testing in this plan: authentik error flow and logout.
Both require real authentik and are handed over as staging tests in Task 7.

---

## File structure

```
dev/
  docker-compose.yml          # netbox (digest pin), postgres, redis, idp; repository at /opt/plugin
  env/netbox.env              # DB/Redis/SECRET_KEY for the test environment
  config/plugins.py           # PLUGINS, PLUGINS_CONFIG, OIDC settings for the dummy IdP
  idp/application/o/netbox/.well-known/openid-configuration   # static discovery JSON
netbox_sso_redirect/
  __init__.py                 # PluginConfig (register middleware)
  conf.py                     # read and validate settings
  redirects.py                # safe_next()
  middleware.py               # SSORedirectMiddleware
  templates/netbox_sso_redirect/bridge.html
  static/netbox_sso_redirect/sso-redirect.js
  tests/__init__.py
  tests/test_smoke.py
  tests/test_conf.py
  tests/test_redirects.py
  tests/test_middleware.py
  tests/test_base_path.py
  tests/test_begin_flow.py
```

**Test commands:**

```bash
# $TEST
docker compose -f dev/docker-compose.yml run --rm netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect --keepdb -v 2
# $TEST_BP — same run with a prefix; only test_base_path is enabled
docker compose -f dev/docker-compose.yml run --rm -e BASE_PATH=netbox/ netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect.tests.test_base_path --keepdb -v 2
```

`docker compose run` overrides CMD and skips netbox-docker's initialization script.
No separate migration command is needed; the test runner creates its own database.

---

### Task 0: Commit the plan

- [ ] `git add docs/superpowers/plans/2026-11-18-netbox-sso-redirect.md docs/superpowers/reviews/2026-11-18-plan.md`,
  `git diff --cached --stat`, `git commit -m "ITSYS-422: Implementation plan and plan review"`.

---

### Task 1: Test environment with netbox-docker

**Files:**

- Create: `dev/docker-compose.yml`, `dev/env/netbox.env`, `dev/config/plugins.py`,
  `dev/idp/application/o/netbox/.well-known/openid-configuration`
- Create: `netbox_sso_redirect/tests/__init__.py`, `netbox_sso_redirect/tests/test_smoke.py`
- Modify README's development section: test commands, image tag, and digest.

**Interfaces:**

- Produces working `$TEST` and `$TEST_BP` commands. The plugin is importable through
  `PYTHONPATH=/opt/plugin`, without container installation. The `idp` service serves discovery at
  `http://idp:9000/application/o/netbox/.well-known/openid-configuration`.

- [ ] **Step 1: Select the image tag and digest**

```bash
TAG=v4.7.3   # if unavailable on Docker Hub, use the latest v4.7.3-* tag
docker pull netboxcommunity/netbox:$TAG
docker inspect --format '{{index .RepoDigests 0}}' netboxcommunity/netbox:$TAG
```

Expected: `netboxcommunity/netbox@sha256:…`. Record the tag as a comment and the digest in Compose.

- [ ] **Step 2: Write `dev/docker-compose.yml`**

Services:

- `postgres`: `postgres:17-alpine`, `POSTGRES_DB/USER/PASSWORD=netbox`.
- `redis`: `valkey/valkey:8-alpine`.
- `idp`: `python:3.12-alpine`, `command: python -m http.server 9000 -d /srv`,
  volume `./idp:/srv:ro`, port `9000:9000`.
- `netbox`: digest from step 1, `env_file: env/netbox.env`, depends on all three,
  volumes `..:/opt/plugin:ro` and `./config/plugins.py:/etc/netbox/config/plugins.py:ro`,
  `environment: PYTHONPATH: /opt/plugin`, port `8000:8080`.

Historical note: the 2026-11-24 security review subsequently restricted both published ports to localhost.

- [ ] **Step 3: Write `dev/env/netbox.env`**

`DB_HOST=postgres`, `DB_NAME=netbox`, `DB_USER=netbox`, `DB_PASSWORD=netbox`,
`REDIS_HOST=redis`, `REDIS_CACHE_HOST=redis`, a development-only `SECRET_KEY`
of at least 50 characters, and `SKIP_SUPERUSER=true`.

- [ ] **Step 4: Write `dev/config/plugins.py` and discovery JSON**

```python
PLUGINS = ["netbox_sso_redirect"]
PLUGINS_CONFIG = {"netbox_sso_redirect": {"backend": "oidc", "local_param": "local"}}
REMOTE_AUTH_BACKEND = "social_core.backends.open_id_connect.OpenIdConnectAuth"
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "http://idp:9000/application/o/netbox"
SOCIAL_AUTH_OIDC_KEY = "netbox-dev"
SOCIAL_AUTH_OIDC_SECRET = "netbox-dev"
```

Discovery JSON: `issuer` is the endpoint above; `authorization_endpoint` is
`http://localhost:9000/authorize` (the browser intentionally receives 404 there).
`token_endpoint`, `userinfo_endpoint`, and `jwks_uri` use `http://idp:9000/…`
and are never called locally.

- [ ] **Step 5: Write the smoke test**

In `tests/test_smoke.py`, class `PluginLoadedTest(TestCase)`:

- `test_plugin_installed`: `apps.is_installed("netbox_sso_redirect")`.
- `test_login_url_from_netbox`: `settings.LOGIN_URL == "/login/"`.
- `test_versions`: `settings.RELEASE.version == "4.7.3"` and
  `importlib.metadata.version("social-auth-core") == "5.2.0"`.
  If the image differs, update test expectations and this plan's tech stack to match and report it.

- [ ] **Step 6: Run tests**

Run `docker compose -f dev/docker-compose.yml up -d postgres redis idp`, then `$TEST`.
Expected: `Ran 3 tests … OK`.

- [ ] **Step 7: Update the README and commit**

Document the expanded `$TEST` and `$TEST_BP` commands, tag, and digest under Development.

```bash
git add dev netbox_sso_redirect/tests README.md
git diff --cached --stat
git commit -m "ITSYS-422: Test environment with netbox-docker"
```

---

### Task 2: Read and validate settings

**Files:**

- Create: `netbox_sso_redirect/conf.py`
- Test: `netbox_sso_redirect/tests/test_conf.py`

**Interfaces:**

- `get_settings() -> tuple[str, str]` returns `(backend, local_param)` using
  `get_plugin_config("netbox_sso_redirect", "backend", "oidc")` and
  `get_plugin_config("netbox_sso_redirect", "local_param", "local")`.
  Pass defaults explicitly: NetBox merges `default_settings` only once at import,
  so `override_settings` would otherwise lose them.
- `validate_settings(backend: str, local_param: str, authentication_backends: list[str]) -> list[str]`
  returns an empty list if valid, otherwise error messages.
  The original plan specified German messages; they were subsequently translated to English.

- [ ] **Step 1: Write tests**

```python
OIDC = ["social_core.backends.open_id_connect.OpenIdConnectAuth",
        "netbox.authentication.ObjectPermissionBackend"]

def test_defaults_are_valid(self):
    self.assertEqual(validate_settings("oidc", "local", OIDC), [])

def test_empty_backend(self):
    self.assertTrue(validate_settings("", "local", OIDC))

def test_empty_local_param(self):
    self.assertTrue(validate_settings("oidc", "", OIDC))

def test_local_param_next_rejected(self):
    self.assertTrue(validate_settings("oidc", "next", OIDC))

def test_backend_not_configured(self):
    self.assertTrue(validate_settings("azuread-oauth2", "local", OIDC))

def test_non_social_backends_ignored(self):
    self.assertTrue(validate_settings("oidc", "local", OIDC[1:]))

def test_backend_cache_untouched(self):
    before = social_core.backends.utils.BACKENDSCACHE
    validate_settings("azuread-oauth2", "local", OIDC)
    self.assertIs(social_core.backends.utils.BACKENDSCACHE, before)

def test_get_settings_defaults(self):
    self.assertEqual(get_settings(), ("oidc", "local"))

@override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": {"backend": "oidc"}})
def test_get_settings_partial_config(self):
    self.assertEqual(get_settings(), ("oidc", "local"))
```

- [ ] **Step 2: Verify failure** — `$TEST` raises ImportError for `netbox_sso_redirect.conf`.
- [ ] **Step 3: Implement `conf.py`**

Validate backends without modifying social-core's global cache. Import each path using
`social_core.utils.module_member` (skip ImportError), retain subclasses of
`social_core.backends.base.BaseAuth`, and match `backend` against their `.name`.
Do not use `load_backends`.

- [ ] **Step 4: Tests pass** — `$TEST` → OK.
- [ ] **Step 5: Commit**

```bash
git add netbox_sso_redirect/conf.py netbox_sso_redirect/tests/test_conf.py
git diff --cached --stat
git commit -m "ITSYS-422: Validate plugin settings"
```

---

### Task 3: Validate `next`

**Files:**

- Create: `netbox_sso_redirect/redirects.py`
- Test: `netbox_sso_redirect/tests/test_redirects.py`

**Interfaces:**

- `safe_next(request: HttpRequest) -> str`: return the last `request.GET["next"]`
  value if `url_has_allowed_host_and_scheme(value, {request.get_host()}, require_https=request.is_secure())`
  succeeds; otherwise return `settings.LOGIN_REDIRECT_URL`.

- [ ] **Step 1: Write tests** using `RequestFactory` and `FALLBACK = settings.LOGIN_REDIRECT_URL`.

| Test | Request | Expected |
|---|---|---|
| `test_relative_path_kept` | `/login/?next=/dcim/devices/` | `/dcim/devices/` |
| `test_same_host_absolute_kept` | `?next=http://testserver/ipam/` | unchanged |
| `test_missing_next` | `/login/` | `FALLBACK` |
| `test_empty_next` | `?next=` | `FALLBACK` |
| `test_protocol_relative` | `?next=//evil.example/` | `FALLBACK` |
| `test_backslash` | `?next=/\evil.example/` | `FALLBACK` |
| `test_encoded_slashes` | `?next=%2F%2Fevil.example%2F` | `FALLBACK` |
| `test_double_encoded_stays_relative` | `?next=%252F%252Fevil.example` | exactly `%2F%2Fevil.example` (relative path, no host) |
| `test_foreign_host` | `?next=https://evil.example/` | `FALLBACK` |
| `test_http_under_https` | `secure=True`, `?next=http://testserver/` | `FALLBACK` |
| `test_repeated_next_uses_last` | `?next=//evil&next=/ipam/` | `/ipam/` |
| `test_repeated_next_last_checked` | `?next=/ipam/&next=//evil` | `FALLBACK` |

- [ ] **Step 2: Verify failure** — `$TEST` → ImportError.
- [ ] **Step 3: Implement `safe_next`.**
- [ ] **Step 4: Tests pass** — `$TEST` → OK.
- [ ] **Step 5: Commit**

```bash
git add netbox_sso_redirect/redirects.py netbox_sso_redirect/tests/test_redirects.py
git diff --cached --stat
git commit -m "ITSYS-422: Validate the next parameter"
```

---

### Task 4: Middleware and bridge page

**Files:**

- Create: `netbox_sso_redirect/middleware.py`,
  `netbox_sso_redirect/templates/netbox_sso_redirect/bridge.html`.
- Modify `netbox_sso_redirect/__init__.py`: register
  `middleware = ["netbox_sso_redirect.middleware.SSORedirectMiddleware"]`
  and remove the placeholder comment.
- Modify README behavior item 1 to describe HTMX handling.
- Tests: `netbox_sso_redirect/tests/test_middleware.py`,
  `netbox_sso_redirect/tests/test_base_path.py`.

**Interfaces:**

- Consumes `get_settings()`, `validate_settings()` from Task 2 and `safe_next()` from Task 3.
- Produces `SSORedirectMiddleware` with `__init__(self, get_response)` and
  `__call__(self, request) -> HttpResponse`.
- Template context for Task 5: `begin_url: str`, `next_url: str`, `local_url: str`
  (`LOGIN_URL?<local_param>=1&next=<next_url>`, encoded with `urlencode`).
  Form ID: `sso-redirect-form`. Error element ID: `sso-redirect-error`, initially hidden.

Behavior:

- Constructor: `validate_settings(*get_settings(), settings.AUTHENTICATION_BACKENDS)`;
  log each error with `logger.warning` on `netbox_sso_redirect`, then raise `MiddlewareNotUsed`.
- Intercept only GET, `request.path == settings.LOGIN_URL` (read at runtime),
  anonymous users, and `request.GET.get(local_param) != "1"`.
  Otherwise call `self.get_response(request)`.
- With `HX-Request`, return an empty 200 response with
  `HX-Redirect: <request.get_full_path()>`. Full navigation drops the HX header,
  so the next request receives the bridge.
- Otherwise render `netbox_sso_redirect/bridge.html`, apply
  `add_never_cache_headers(response)`, and set `X-Frame-Options: DENY`.
- The original `bridge.html` design is standalone HTML, without NetBox template inheritance:
  `{% csrf_token %}`, an auto-escaped hidden `next` input, a visible "Sign in with SSO"
  button, a "Local login" link to `local_url`, and
  `{% static 'netbox_sso_redirect/sso-redirect.js' %}` with `defer`.
  The script arrives in Task 5; NetBox's `StaticFilesStorage` allows rendering before it exists.

- [ ] **Step 1: Write `test_middleware.py`**

In `setUpTestData`, create ordinary `self.user` and superuser `self.admin` with an API
token. Read `users/models/tokens.py` in the container
(`docker compose … run --rm netbox cat /opt/netbox/netbox/users/models/tokens.py`)
and use the token model/header format required by NetBox 4.7.3.

```python
BRIDGE = "netbox_sso_redirect/bridge.html"

def test_anonymous_get_login_renders_bridge(self):
    r = self.client.get("/login/?next=/dcim/devices/")
    self.assertEqual(r.status_code, 200)
    self.assertTemplateUsed(r, BRIDGE)
    self.assertContains(r, f'action="{reverse("social_auth_begin", args=["oidc"])}"')
    self.assertContains(r, 'name="csrfmiddlewaretoken"')
    self.assertContains(r, 'name="next" value="/dcim/devices/"')
    self.assertContains(r, 'href="/login/?local=1&amp;next=%2Fdcim%2Fdevices%2F"')

def test_bridge_headers(self):
    r = self.client.get("/login/")
    self.assertIn("no-store", r["Cache-Control"])
    self.assertIn("private", r["Cache-Control"])
    self.assertEqual(r["X-Frame-Options"], "DENY")

def test_next_is_escaped(self):
    r = self.client.get('/login/?next=/x"><script>')
    self.assertContains(r, 'name="next" value="/x&quot;&gt;&lt;script&gt;"')
    self.assertNotContains(r, '"><script>')

def test_local_1_shows_netbox_form(self):
    r = self.client.get("/login/?local=1")
    self.assertTemplateUsed(r, "login.html")
    self.assertContains(r, 'name="password"')

def test_local_variants_render_bridge(self):
    for q in ("local=0", "local=", "LOCAL=1", "local=true"):
        with self.subTest(q=q):
            self.assertTemplateUsed(self.client.get(f"/login/?{q}"), BRIDGE)

def test_authenticated_user_passes_through(self):
    self.client.force_login(self.user)
    r = self.client.get("/login/?next=/ipam/")
    self.assertTemplateNotUsed(r, BRIDGE)

def test_head_passes_through(self):
    r = self.client.head("/login/")
    self.assertTemplateNotUsed(r, BRIDGE)
    self.assertTemplateUsed(r, "login.html")

def test_post_login_without_local_reaches_netbox(self):
    r = self.client.post("/login/", {"username": "x", "password": "y"})
    self.assertTemplateUsed(r, "login.html")
    self.assertContains(r, 'name="password"')

def test_htmx_on_login_gets_hx_redirect(self):
    r = self.client.get("/login/?next=/dcim/", headers={"HX-Request": "true"})
    self.assertEqual(r.status_code, 200)
    self.assertEqual(r["HX-Redirect"], "/login/?next=/dcim/")
    self.assertTemplateNotUsed(r, BRIDGE)

def test_htmx_expired_session_full_navigation(self):
    r = self.client.get("/dcim/devices/", headers={"HX-Request": "true"})
    self.assertEqual(r.status_code, 302)
    hop = self.client.get(r["Location"], headers={"HX-Request": "true"})
    self.assertEqual(hop["HX-Redirect"], r["Location"])
    self.assertIn("next=%2Fdcim%2Fdevices%2F", hop["HX-Redirect"])
    self.assertTemplateUsed(self.client.get(hop["HX-Redirect"]), BRIDGE)

def test_other_paths_untouched(self):
    cases = {"/oauth/login/oidc/": 405, "/dcim/devices/": 302}
    for path, status in cases.items():
        with self.subTest(path=path):
            r = self.client.get(path)
            self.assertEqual(r.status_code, status)
            self.assertTemplateNotUsed(r, BRIDGE)

def test_api_with_valid_token(self):
    r = self.client.get("/api/dcim/sites/", headers={"Authorization": <valid token header>,
                                                     "Accept": "application/json"})
    self.assertEqual(r.status_code, 200)
    self.assertEqual(r["Content-Type"], "application/json")

def test_api_with_invalid_token(self):
    r = self.client.get("/api/dcim/sites/", headers={"Authorization": <invalid token header>,
                                                     "Accept": "application/json"})
    self.assertEqual(r.status_code, 403)
    self.assertTemplateNotUsed(r, BRIDGE)

@override_settings(LOGIN_URL="/anmelden/")
def test_login_url_read_at_runtime(self):
    self.assertTemplateUsed(self.client.get("/anmelden/"), BRIDGE)
    self.assertTemplateNotUsed(self.client.get("/login/"), BRIDGE)

def test_invalid_settings_raise_middleware_not_used(self):
    for cfg in ({"backend": "nope", "local_param": "local"},
                {"backend": "oidc", "local_param": "next"}):
        with self.subTest(cfg=cfg), override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": cfg}):
            with self.assertLogs("netbox_sso_redirect", "WARNING"), self.assertRaises(MiddlewareNotUsed):
                SSORedirectMiddleware(lambda r: HttpResponse())

def test_invalid_settings_full_stack_falls_back_to_netbox_login(self):
    for cfg in ({"backend": "nope", "local_param": "local"},
                {"backend": "oidc", "local_param": "next"}):
        with self.subTest(cfg=cfg), override_settings(PLUGINS_CONFIG={"netbox_sso_redirect": cfg}):
            with self.assertLogs("netbox_sso_redirect", "WARNING"):
                r = Client().get("/login/")   # new client = new handler = new middleware chain
            self.assertEqual(r.status_code, 200)
            self.assertTemplateUsed(r, "login.html")
            self.assertTemplateNotUsed(r, BRIDGE)
```

If NetBox 4.7.3 returns a different status in `test_api_with_invalid_token` or
`test_other_paths_untouched` (for example 401 rather than 403), record the observed
NetBox status. It must not return the bridge or redirect to `/login/`.

- [ ] **Step 2: Write `test_base_path.py`**

Use `@skipUnless(settings.BASE_PATH == "netbox/", "only with $TEST_BP")`
on `BasePathTest(TestCase)`:

```python
def test_bridge_with_prefix(self):
    r = self.client.get("/netbox/login/")
    self.assertTemplateUsed(r, BRIDGE)
    self.assertContains(r, 'action="/netbox/oauth/begin/oidc/"')
    self.assertContains(r, '/netbox/static/netbox_sso_redirect/sso-redirect.js')
    self.assertContains(r, 'href="/netbox/login/?local=1&amp;next=%2Fnetbox%2F"')
    self.assertContains(r, 'name="next" value="/netbox/"')   # LOGIN_REDIRECT_URL fallback

def test_local_with_prefix(self):
    self.assertTemplateUsed(self.client.get("/netbox/login/?local=1"), "login.html")
```

- [ ] **Step 3: Verify failure** — bridge tests fail because the template is not used.
- [ ] **Step 4: Implement middleware and bridge; register middleware in `__init__.py`.**
- [ ] **Step 5: Tests pass** — `$TEST` includes Tasks 1–3 and skips `test_base_path`;
  then `$TEST_BP` passes the prefix tests.
- [ ] **Step 6: README** — add to item 1 that HTMX receives `HX-Redirect` for full navigation.
- [ ] **Step 7: Commit**

```bash
git add netbox_sso_redirect/middleware.py netbox_sso_redirect/templates netbox_sso_redirect/__init__.py \
        netbox_sso_redirect/tests/test_middleware.py netbox_sso_redirect/tests/test_base_path.py README.md
git diff --cached --stat
git commit -m "ITSYS-422: Middleware and bridge page"
```

---

### Task 5: Script and SSO start integration

**Files:**

- Create: `netbox_sso_redirect/static/netbox_sso_redirect/sso-redirect.js`
- Test: `netbox_sso_redirect/tests/test_begin_flow.py`

**Interfaces:**

- Consumes form `#sso-redirect-form` and error element `#sso-redirect-error` from Task 4.

Script without framework or build step:
on `DOMContentLoaded`, call `fetch(form.action, {method: "POST", body: new FormData(form),
headers: {Accept: "application/json"}, credentials: "same-origin"})`.
A response with `url` navigates through `location.assign(url)`.
A response with `html`, an error, or a non-OK status reveals `#sso-redirect-error`
by removing `hidden` and focuses the button. No automatic second attempt.

- [ ] **Step 1: Write the integration test**

Use `Client(enforce_csrf_checks=True)`. Since `oidc_config` is a method decorated
with `@cache`, patch its **`return_value`**:

```python
IDP = {"authorization_endpoint": "https://idp.example/authorize"}

@mock.patch.object(OpenIdConnectAuth, "oidc_config", return_value=IDP)
def _begin(self, _mock, next_url="/dcim/devices/"):
    bridge = self.client.get(f"/login/?next={next_url}")
    token = re.search(r'name="csrfmiddlewaretoken" value="([^"]+)"', bridge.content.decode())[1]
    return self.client.post(reverse("social_auth_begin", args=["oidc"]),
                            {"csrfmiddlewaretoken": token, "next": next_url},
                            headers={"Accept": "application/json"})

def test_begin_returns_idp_url_as_json(self):
    r = self._begin()
    self.assertEqual(r.status_code, 200)
    self.assertTrue(r.json()["url"].startswith("https://idp.example/authorize"))

def test_begin_stores_next_in_session(self):
    self._begin()
    self.assertEqual(self.client.session["next"], "/dcim/devices/")

def test_begin_without_token_is_rejected(self):
    r = self.client.post(reverse("social_auth_begin", args=["oidc"]), {"next": "/"},
                         headers={"Accept": "application/json"})
    self.assertEqual(r.status_code, 403)

def test_script_is_collectable(self):
    self.assertIsNotNone(finders.find("netbox_sso_redirect/sso-redirect.js"))
```

- [ ] **Step 2: Verify failure** — only `test_script_is_collectable` should fail.
  If `test_begin_stores_next_in_session` fails while `test_begin_returns_idp_url_as_json`
  passes, stop and report: social-core is not preserving `next` as assumed.
- [ ] **Step 3: Write `sso-redirect.js`.**
- [ ] **Step 4: Tests pass** — `$TEST` → OK.
- [ ] **Step 5: Manual browser check**

Run `docker compose -f dev/docker-compose.yml up -d`, then once:
`docker compose -f dev/docker-compose.yml exec netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate`
and `… collectstatic --no-input`. Open `http://localhost:8000/`.
Expect `/login/?next=/` followed by `http://localhost:9000/authorize?…` (404 is expected).
The console should contain no CSP or JavaScript errors.
With JavaScript disabled, the button and "Local login" link remain visible.
`/login/?local=1` shows the NetBox form. Briefly record the result in the commit message.

- [ ] **Step 6: Commit**

```bash
git add netbox_sso_redirect/static netbox_sso_redirect/tests/test_begin_flow.py
git diff --cached --stat
git commit -m "ITSYS-422: Start SSO with fetch under CSP form-action"
```

---

### Task 6: Release 0.1.0

**Files:**

- Modify README status to describe the implementation and require `collectstatic`
  after installation in the image.
- Modify `pyproject.toml` if needed: `[tool.setuptools.package-data]`.

- [ ] **Step 1: Build the wheel in isolation**

Install `build` in a virtual environment outside the repository, then run
`python -m build --wheel` inside it. Expect
`dist/netbox_sso_redirect-0.1.0-py3-none-any.whl`.
`python -m zipfile -l dist/*.whl` must list `bridge.html` and `sso-redirect.js`.
If missing, as expected initially, add
`[tool.setuptools.package-data] netbox_sso_redirect = ["templates/**/*", "static/**/*"]`,
rebuild, and verify again.

- [ ] **Step 2: Full test run** — `$TEST` and `$TEST_BP` → OK.
- [ ] **Step 3: Commit**

```bash
git add README.md pyproject.toml
git diff --cached --stat
git commit -m "ITSYS-422: Release 0.1.0"
git status --short   # must be empty (dist/ and build/ are ignored)
```

- [ ] **Step 4: Tag** — `git tag -a v0.1.0 -m "v0.1.0"`; record the SHA
  with `git rev-parse "v0.1.0^{commit}"`.
- [ ] **Step 5: Push only after Christian's approval** — `git push origin main --follow-tags`.

---

### Task 7: Handoff to docker-netbox-wus

Do not modify the image repository here. Write the handoff to
`~/projects/_handoff/<docker-netbox-wus-directory-name>/2026-11-18-netbox-sso-redirect.md`.
Verify the receiving project's directory name under `~/projects` first and create
the destination folder if needed.

- [ ] **Step 1: Write a handoff** covering:
  - `plugin_requirements.txt`: `git+https://github.com/wus-technik/netbox-sso-redirect@<SHA>  # v0.1.0`
  - Supply the read token only through a BuildKit secret for a single command,
    without retaining a file in the image:

    ```dockerfile
    RUN --mount=type=secret,id=gh_token \
        GIT_CONFIG_COUNT=1 \
        GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
        GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$(cat /run/secrets/gh_token)" | base64 -w0)" \
        /opt/netbox/venv/bin/pip install --no-cache-dir -r /opt/netbox/plugin_requirements.txt
    ```

    No `git config --global`, `--build-arg`, token in the URL, or `set -x`.
    Inspect the finished image: search for the token prefix in `/root/.gitconfig`,
    `/opt/netbox/venv/**/direct_url.json`, and build logs; expect no matches.
  - Enable the plugin in `configuration/plugins.py`; run `collectstatic` after installation.
  - Set `SOCIAL_AUTH_LOGIN_ERROR_URL` to `LOGIN_URL` plus `?local=1`, including `BASE_PATH`.
  - Keep `LOGIN_FORM_HIDDEN = False`.
  - Point `LOGOUT_REDIRECT_URL` to authentik's end-session URL; do not land on `/login/`.
  - Proxy: overwrite `X-Forwarded-*`, check `ALLOWED_HOSTS` and
    `CSRF_TRUSTED_ORIGINS`, and record CSP.
  - Staging tests not covered locally: login with `next`; authentik error to
    `/login/?local=1`; logout without `id_token_hint` ends the authentik session;
    local login through `?local=1`; no browser CSP errors.
- [ ] **Step 2: Comment on Jira ITSYS-422** that the plugin is complete and the handoff is available.
