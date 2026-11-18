# netbox-sso-redirect – Implementierungsplan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Ziel:** Ein nicht angemeldeter GET auf `LOGIN_URL` startet sofort den OIDC-Login gegen authentik;
das lokale Formular bleibt über `?local=1` erreichbar.

**Architektur:** Eine Middleware (über `PluginConfig.middleware`) fängt den GET auf `LOGIN_URL`
ab und rendert eine Brückenseite. Die Seite schickt per `fetch` mit `Accept: application/json`
einen POST (CSRF-Token, geprüftes `next`) an NetBox' `social_auth_begin` und folgt der
zurückgelieferten URL. Alles andere geht unverändert an NetBox.

**Tech Stack:** Python 3.12, Django (wie in NetBox 4.7.3), social-auth-app-django 6.1.0 /
social-auth-core 5.2.0 (von NetBox 4.7.3 gepinnt), netbox-docker (Docker Desktop),
Django-Testrunner `manage.py test`.

**Spec:** `README.md` (Abschnitte „Geplantes Verhalten“, „Im Image“, „Entwicklung“). Reviews:
`docs/superpowers/reviews/2026-11-18-spec-readme.md`, `docs/superpowers/reviews/2026-11-18-plan.md`.
Ref: ITSYS-422.

## Global Constraints

- NetBox `min_version = "4.7.0"`, `max_version = "4.7.99"` – nicht ändern.
- `__version__` bleibt ein String-Literal in `netbox_sso_redirect/__init__.py`.
- Einstellungen in `PLUGINS_CONFIG['netbox_sso_redirect']`: `backend` (Standard `oidc`),
  `local_param` (Standard `local`).
- Ziel des SSO-POST: `reverse('social_auth_begin', args=[backend])`, nie `social:begin`, nie ein
  fester Pfad.
- Kein Inline-JavaScript; das Skript liegt unter `static/netbox_sso_redirect/`.
- Brückenseite: `Cache-Control` enthält `no-store` und `private`; `X-Frame-Options: DENY`.
- Rückfallziel für ungültiges oder fehlendes `next`: `settings.LOGIN_REDIRECT_URL`.
- Keine neuen Laufzeitabhängigkeiten außer dem, was NetBox mitbringt.
- Jeder Commit: erst `git add <Dateien des Tasks>`, dann `git diff --cached --stat` prüfen, dann
  `git commit`. Nachrichten auf Deutsch, `ITSYS-422` im Betreff, ohne KI-Co-Author-Trailer.

## Review Focus

1. **Abgelaufene Sitzung während einer HTMX-Anfrage** → volle Navigation zum SSO, nicht die
   Brückenseite als Fragment. Test in Task 4 (`test_htmx_expired_session_full_navigation`).
2. **`next` mit Fremdhost in Varianten** (`//evil`, `/\evil`, `%2F%2Fevil`, `http://` unter HTTPS)
   → Rückfall auf `LOGIN_REDIRECT_URL`. Tests in Task 3.
3. **Fehlkonfiguration** (falsches `backend`, `local_param = "next"`, Teil-Konfiguration) → kein
   500, kein Kreisel, sondern normaler NetBox-Login plus Log-Warnung. Tests in Task 2 und 4.
4. **`BASE_PATH` gesetzt** → Begin-URL, Skript-URL, Lokal-Link und Rückfallziel tragen das
   Präfix. Test in Task 4 (eigener Lauf `$TEST_BP`).
5. **`local`-Varianten** (`local=0`, `local=`, `LOCAL=1`) → Brückenseite; nur genau `local=1`
   zeigt das Formular. Test in Task 4.

Bewusst nicht lokal getestet: Fehlerpfad von authentik und Abmelden – beides braucht echtes
authentik und wird in Task 7 als Staging-Test übergeben.

---

## Dateistruktur

```
dev/
  docker-compose.yml          # netbox (Digest-Pin), postgres, redis, idp; Repo nach /opt/plugin
  env/netbox.env              # DB/Redis/SECRET_KEY für die Testumgebung
  config/plugins.py           # PLUGINS, PLUGINS_CONFIG, OIDC-Werte gegen den Dummy-IdP
  idp/application/o/netbox/.well-known/openid-configuration   # statisches Discovery-JSON
netbox_sso_redirect/
  __init__.py                 # PluginConfig (middleware eintragen)
  conf.py                     # Einstellungen lesen und prüfen
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

**Testbefehle:**

```bash
# $TEST
docker compose -f dev/docker-compose.yml run --rm netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect --keepdb -v 2
# $TEST_BP – derselbe Lauf mit Präfix; nur test_base_path läuft dann scharf
docker compose -f dev/docker-compose.yml run --rm -e BASE_PATH=netbox/ netbox \
  /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect.tests.test_base_path --keepdb -v 2
```

`docker compose run` überschreibt das CMD und überspringt damit das Init-Skript von
netbox-docker; Migrationen sind nicht nötig, der Testrunner legt seine eigene Datenbank an.

---

### Task 0: Plan committen

- [ ] `git add docs/superpowers/plans/2026-11-18-netbox-sso-redirect.md docs/superpowers/reviews/2026-11-18-plan.md`,
  `git diff --cached --stat`, `git commit -m "ITSYS-422: Implementierungsplan und Plan-Review"`.

---

### Task 1: Testumgebung mit netbox-docker

**Files:**
- Create: `dev/docker-compose.yml`, `dev/env/netbox.env`, `dev/config/plugins.py`,
  `dev/idp/application/o/netbox/.well-known/openid-configuration`
- Create: `netbox_sso_redirect/tests/__init__.py`, `netbox_sso_redirect/tests/test_smoke.py`
- Modify: `README.md` (Abschnitt „Entwicklung“: Testbefehle, Image-Tag und Digest)

**Interfaces:**
- Produces: `$TEST` und `$TEST_BP` laufen; Plugin ist über `PYTHONPATH=/opt/plugin` importierbar
  (keine Installation im Container). Dienst `idp` liefert das Discovery-JSON unter
  `http://idp:9000/application/o/netbox/.well-known/openid-configuration`.

- [ ] **Step 1: Image-Tag und Digest festlegen**

```bash
TAG=v4.7.3   # fehlt der Tag auf Docker Hub: neuesten v4.7.3-*-Tag einsetzen
docker pull netboxcommunity/netbox:$TAG
docker inspect --format '{{index .RepoDigests 0}}' netboxcommunity/netbox:$TAG
```

Expected: `netboxcommunity/netbox@sha256:…`. Tag (als Kommentar) und Digest in die Compose-Datei.

- [ ] **Step 2: `dev/docker-compose.yml` schreiben**

Dienste:
- `postgres` (`postgres:17-alpine`, `POSTGRES_DB/USER/PASSWORD=netbox`),
- `redis` (`valkey/valkey:8-alpine`),
- `idp` (`python:3.12-alpine`, `command: python -m http.server 9000 -d /srv`,
  Volume `./idp:/srv:ro`, Port `9000:9000`),
- `netbox` (Digest aus Step 1, `env_file: env/netbox.env`, `depends_on` alle drei, Volumes
  `..:/opt/plugin:ro` und `./config/plugins.py:/etc/netbox/config/plugins.py:ro`,
  `environment: PYTHONPATH: /opt/plugin`, Port `8000:8080`).

- [ ] **Step 3: `dev/env/netbox.env` schreiben**

`DB_HOST=postgres`, `DB_NAME=netbox`, `DB_USER=netbox`, `DB_PASSWORD=netbox`, `REDIS_HOST=redis`,
`REDIS_CACHE_HOST=redis`, `SECRET_KEY` (beliebig, ≥ 50 Zeichen, nur für Dev), `SKIP_SUPERUSER=true`.

- [ ] **Step 4: `dev/config/plugins.py` und Discovery-JSON schreiben**

```python
PLUGINS = ["netbox_sso_redirect"]
PLUGINS_CONFIG = {"netbox_sso_redirect": {"backend": "oidc", "local_param": "local"}}
REMOTE_AUTH_BACKEND = "social_core.backends.open_id_connect.OpenIdConnectAuth"
SOCIAL_AUTH_OIDC_OIDC_ENDPOINT = "http://idp:9000/application/o/netbox"
SOCIAL_AUTH_OIDC_KEY = "netbox-dev"
SOCIAL_AUTH_OIDC_SECRET = "netbox-dev"
```

Discovery-JSON: `issuer` = Endpoint oben, `authorization_endpoint` =
`http://localhost:9000/authorize` (Browser landet dort auf 404 – gewollt), `token_endpoint`,
`userinfo_endpoint`, `jwks_uri` auf `http://idp:9000/…` (werden lokal nie aufgerufen).

- [ ] **Step 5: Smoke-Test schreiben**

`tests/test_smoke.py`, `class PluginLoadedTest(TestCase)`:
- `test_plugin_installed` → `apps.is_installed("netbox_sso_redirect")`;
- `test_login_url_from_netbox` → `settings.LOGIN_URL == "/login/"`;
- `test_versions` → `settings.RELEASE.version == "4.7.3"` und
  `importlib.metadata.version("social-auth-core") == "5.2.0"` (weicht das Image ab: Werte im Test
  und im Tech Stack dieses Plans auf das Image anpassen und melden).

- [ ] **Step 6: Tests laufen lassen**

Run: `docker compose -f dev/docker-compose.yml up -d postgres redis idp`, dann `$TEST`.
Expected: `Ran 3 tests … OK`.

- [ ] **Step 7: README ergänzen und committen**

In „Entwicklung“ `$TEST`, `$TEST_BP` (ausgeschrieben), Tag und Digest eintragen.

```bash
git add dev netbox_sso_redirect/tests README.md
git diff --cached --stat
git commit -m "ITSYS-422: Testumgebung mit netbox-docker"
```

---

### Task 2: Einstellungen lesen und prüfen

**Files:**
- Create: `netbox_sso_redirect/conf.py`
- Test: `netbox_sso_redirect/tests/test_conf.py`

**Interfaces:**
- Produces:
  - `get_settings() -> tuple[str, str]` – `(backend, local_param)` über
    `get_plugin_config("netbox_sso_redirect", "backend", "oidc")` bzw. `(…, "local_param", "local")`.
    Die Standardwerte stehen explizit im Aufruf, weil NetBox `default_settings` nur einmal beim
    Import der Settings einmischt und ein `override_settings` sie sonst verliert.
  - `validate_settings(backend: str, local_param: str, authentication_backends: list[str]) -> list[str]`
    – leere Liste = gültig, sonst deutsche Fehlermeldungen.

- [ ] **Step 1: Tests schreiben**

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

- [ ] **Step 2: Fehlschlag prüfen** – `$TEST` → ImportError für `netbox_sso_redirect.conf`.

- [ ] **Step 3: `conf.py` implementieren**

Backend-Prüfung ohne den globalen Cache von social-core: jeden Pfad mit
`social_core.utils.module_member` importieren (ImportError → überspringen), nur Unterklassen von
`social_core.backends.base.BaseAuth` behalten, `backend` muss deren `.name` entsprechen.
`load_backends` nicht verwenden.

- [ ] **Step 4: Tests grün** – `$TEST` → OK.

- [ ] **Step 5: Commit**

```bash
git add netbox_sso_redirect/conf.py netbox_sso_redirect/tests/test_conf.py
git diff --cached --stat
git commit -m "ITSYS-422: Plugin-Einstellungen prüfen"
```

---

### Task 3: `next` prüfen

**Files:**
- Create: `netbox_sso_redirect/redirects.py`
- Test: `netbox_sso_redirect/tests/test_redirects.py`

**Interfaces:**
- Produces: `safe_next(request: HttpRequest) -> str` – letzter Wert von `request.GET["next"]`,
  wenn `url_has_allowed_host_and_scheme(value, {request.get_host()}, require_https=request.is_secure())`,
  sonst `settings.LOGIN_REDIRECT_URL`.

- [ ] **Step 1: Tests schreiben** (mit `RequestFactory`; `FALLBACK = settings.LOGIN_REDIRECT_URL`)

| Test | Request | Erwartet |
|---|---|---|
| `test_relative_path_kept` | `/login/?next=/dcim/devices/` | `/dcim/devices/` |
| `test_same_host_absolute_kept` | `?next=http://testserver/ipam/` | unverändert |
| `test_missing_next` | `/login/` | `FALLBACK` |
| `test_empty_next` | `?next=` | `FALLBACK` |
| `test_protocol_relative` | `?next=//evil.example/` | `FALLBACK` |
| `test_backslash` | `?next=/\evil.example/` | `FALLBACK` |
| `test_encoded_slashes` | `?next=%2F%2Fevil.example%2F` | `FALLBACK` |
| `test_double_encoded_stays_relative` | `?next=%252F%252Fevil.example` | genau `%2F%2Fevil.example` (relativer Pfad, kein Host) |
| `test_foreign_host` | `?next=https://evil.example/` | `FALLBACK` |
| `test_http_under_https` | `secure=True`, `?next=http://testserver/` | `FALLBACK` |
| `test_repeated_next_uses_last` | `?next=//evil&next=/ipam/` | `/ipam/` |
| `test_repeated_next_last_checked` | `?next=/ipam/&next=//evil` | `FALLBACK` |

- [ ] **Step 2: Fehlschlag prüfen** – `$TEST` → ImportError.
- [ ] **Step 3: `safe_next` implementieren.**
- [ ] **Step 4: Tests grün** – `$TEST` → OK.
- [ ] **Step 5: Commit**

```bash
git add netbox_sso_redirect/redirects.py netbox_sso_redirect/tests/test_redirects.py
git diff --cached --stat
git commit -m "ITSYS-422: next-Parameter prüfen"
```

---

### Task 4: Middleware und Brückenseite

**Files:**
- Create: `netbox_sso_redirect/middleware.py`,
  `netbox_sso_redirect/templates/netbox_sso_redirect/bridge.html`
- Modify: `netbox_sso_redirect/__init__.py` (`middleware = ["netbox_sso_redirect.middleware.SSORedirectMiddleware"]`, Kommentar „folgt“ entfernen)
- Modify: `README.md` („Geplantes Verhalten“ Punkt 1: HTMX-Verhalten ergänzen)
- Test: `netbox_sso_redirect/tests/test_middleware.py`, `netbox_sso_redirect/tests/test_base_path.py`

**Interfaces:**
- Consumes: `get_settings()`, `validate_settings()` (Task 2), `safe_next()` (Task 3).
- Produces: `class SSORedirectMiddleware` mit `__init__(self, get_response)` und
  `__call__(self, request) -> HttpResponse`. Template-Kontext für Task 5:
  `begin_url: str`, `next_url: str`, `local_url: str` (`LOGIN_URL?<local_param>=1&next=<next_url>`,
  mit `urlencode`). Das Formular hat `id="sso-redirect-form"`, das Fehlerelement
  `id="sso-redirect-error"` (anfangs mit `hidden`).

Verhalten:
- `__init__`: `validate_settings(*get_settings(), settings.AUTHENTICATION_BACKENDS)`; bei Fehlern
  je eine `logger.warning` (Logger `netbox_sso_redirect`) und `raise MiddlewareNotUsed`.
- `__call__` greift nur, wenn `request.method == "GET"`, `request.path == settings.LOGIN_URL`
  (zur Laufzeit gelesen), `not request.user.is_authenticated` und
  `request.GET.get(local_param) != "1"`. Sonst `self.get_response(request)`.
- Bei `HX-Request`-Header: leere 200-Antwort mit `HX-Redirect: <request.get_full_path()>` (volle
  Navigation statt Fragment; die Folgeanfrage hat keinen HX-Header und bekommt die Brückenseite).
- Sonst `render(request, "netbox_sso_redirect/bridge.html", ctx)`, danach
  `add_never_cache_headers(response)` und `response["X-Frame-Options"] = "DENY"`.
- `bridge.html`: eigenständiges HTML (erbt nicht von NetBox-Templates), `{% csrf_token %}`,
  `<input type="hidden" name="next" value="{{ next_url }}">` (Auto-Escaping), sichtbarer
  Submit-Knopf „Mit SSO anmelden“, Link „Lokale Anmeldung“ auf `local_url`, Skript per
  `{% static 'netbox_sso_redirect/sso-redirect.js' %}` mit `defer`. Die Datei kommt in Task 5;
  NetBox nutzt `StaticFilesStorage`, das Fehlen stört das Rendern nicht.

- [ ] **Step 1: Tests in `test_middleware.py` schreiben**

`setUpTestData`: normaler Nutzer `self.user`; Superuser `self.admin` mit API-Token. Token-Modell
und Header-Format aus `users/models/tokens.py` im Container ablesen
(`docker compose … run --rm netbox cat /opt/netbox/netbox/users/models/tokens.py`) und im Test so
verwenden, wie NetBox 4.7.3 sie vorgibt.

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
    r = self.client.get("/api/dcim/sites/", headers={"Authorization": <gültiger Token-Header>,
                                                     "Accept": "application/json"})
    self.assertEqual(r.status_code, 200)
    self.assertEqual(r["Content-Type"], "application/json")

def test_api_with_invalid_token(self):
    r = self.client.get("/api/dcim/sites/", headers={"Authorization": <ungültiger Token-Header>,
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
                r = Client().get("/login/")   # neuer Client = neuer Handler = neue Middleware-Kette
            self.assertEqual(r.status_code, 200)
            self.assertTemplateUsed(r, "login.html")
            self.assertTemplateNotUsed(r, BRIDGE)
```

Weicht der Status in `test_api_with_invalid_token` oder `test_other_paths_untouched` bei NetBox
4.7.3 ab (z. B. 401 statt 403), den beobachteten NetBox-Wert eintragen – entscheidend ist, dass es
nicht die Brückenseite ist und kein Redirect auf `/login/`.

- [ ] **Step 2: Test `test_base_path.py` schreiben**

`@skipUnless(settings.BASE_PATH == "netbox/", "nur mit $TEST_BP")`, Klasse `BasePathTest(TestCase)`:

```python
def test_bridge_with_prefix(self):
    r = self.client.get("/netbox/login/")
    self.assertTemplateUsed(r, BRIDGE)
    self.assertContains(r, 'action="/netbox/oauth/begin/oidc/"')
    self.assertContains(r, '/netbox/static/netbox_sso_redirect/sso-redirect.js')
    self.assertContains(r, 'href="/netbox/login/?local=1&amp;next=%2Fnetbox%2F"')
    self.assertContains(r, 'name="next" value="/netbox/"')   # Rückfall LOGIN_REDIRECT_URL

def test_local_with_prefix(self):
    self.assertTemplateUsed(self.client.get("/netbox/login/?local=1"), "login.html")
```

- [ ] **Step 3: Fehlschlag prüfen** – `$TEST` → Bridge-Tests schlagen fehl (Template nicht benutzt).
- [ ] **Step 4: `middleware.py`, `bridge.html` implementieren, Middleware in `__init__.py` eintragen.**
- [ ] **Step 5: Tests grün** – `$TEST` → OK (inklusive Task 1–3; `test_base_path` wird
  übersprungen), dann `$TEST_BP` → `test_base_path` OK.
- [ ] **Step 6: README** – Punkt 1 um einen Satz ergänzen: HTMX-Anfragen bekommen `HX-Redirect`
  statt der Brückenseite, damit der Browser ganz neu navigiert.
- [ ] **Step 7: Commit**

```bash
git add netbox_sso_redirect/middleware.py netbox_sso_redirect/templates netbox_sso_redirect/__init__.py \
        netbox_sso_redirect/tests/test_middleware.py netbox_sso_redirect/tests/test_base_path.py README.md
git diff --cached --stat
git commit -m "ITSYS-422: Middleware und Brückenseite"
```

---

### Task 5: Skript und SSO-Start ende-zu-ende

**Files:**
- Create: `netbox_sso_redirect/static/netbox_sso_redirect/sso-redirect.js`
- Test: `netbox_sso_redirect/tests/test_begin_flow.py`

**Interfaces:**
- Consumes: Formular `#sso-redirect-form`, Fehlerelement `#sso-redirect-error` (Task 4).

Skript (kein Framework, kein Build):
`DOMContentLoaded` → `fetch(form.action, {method: "POST", body: new FormData(form),
headers: {Accept: "application/json"}, credentials: "same-origin"})`. Antwort mit `url` →
`location.assign(url)`. Antwort mit `html` oder Fehler/Nicht-OK-Status → `#sso-redirect-error`
sichtbar machen (`hidden` entfernen) und den Knopf fokussieren; kein automatischer zweiter Versuch.

- [ ] **Step 1: Integrationstest schreiben**

`self.client = Client(enforce_csrf_checks=True)`. `oidc_config` ist eine Methode mit
`@cache`-Dekorator; deshalb **`return_value`** patchen:

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

- [ ] **Step 2: Fehlschlag prüfen** – `$TEST` → nur `test_script_is_collectable` schlägt fehl.
  Schlägt zusätzlich `test_begin_stores_next_in_session` fehl, obwohl `test_begin_returns_idp_url_as_json`
  grün ist: stoppen und melden – dann übernimmt social-core `next` nicht wie angenommen.
- [ ] **Step 3: `sso-redirect.js` schreiben.**
- [ ] **Step 4: Tests grün** – `$TEST` → OK.
- [ ] **Step 5: Manuelle Prüfung im Browser**

`docker compose -f dev/docker-compose.yml up -d`; einmalig
`docker compose -f dev/docker-compose.yml exec netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py migrate`
und `… collectstatic --no-input`. `http://localhost:8000/` öffnen. Expected: über `/login/?next=/`
weiter auf `http://localhost:9000/authorize?…` (404 dort ist richtig). Browser-Konsole ohne CSP-
oder JS-Fehler. Mit deaktiviertem JavaScript: Knopf und Link „Lokale Anmeldung“ sichtbar.
`/login/?local=1` zeigt das NetBox-Formular. Ergebnis kurz im Commit-Text festhalten.

- [ ] **Step 6: Commit**

```bash
git add netbox_sso_redirect/static netbox_sso_redirect/tests/test_begin_flow.py
git diff --cached --stat
git commit -m "ITSYS-422: SSO-Start per fetch gegen CSP form-action"
```

---

### Task 6: Release 0.1.0

**Files:**
- Modify: `README.md` (Status: Umsetzung vorhanden; Hinweis, dass das Image nach der Installation
  `collectstatic` ausführen muss)
- Modify ggf.: `pyproject.toml` (`[tool.setuptools.package-data]`)

- [ ] **Step 1: Wheel isoliert bauen**

In einer venv außerhalb des Repos `pip install build`, dann im Repo `python -m build --wheel`.
Expected: `dist/netbox_sso_redirect-0.1.0-py3-none-any.whl`; `python -m zipfile -l dist/*.whl`
zeigt `bridge.html` und `sso-redirect.js`. Fehlen sie (zu erwarten):
`[tool.setuptools.package-data] netbox_sso_redirect = ["templates/**/*", "static/**/*"]`
ergänzen, neu bauen, erneut prüfen.

- [ ] **Step 2: Kompletter Testlauf** – `$TEST` und `$TEST_BP` → OK.
- [ ] **Step 3: Commit**

```bash
git add README.md pyproject.toml
git diff --cached --stat
git commit -m "ITSYS-422: Release 0.1.0"
git status --short   # muss leer sein (dist/ und build/ sind ignoriert)
```

- [ ] **Step 4: Tag** – `git tag -a v0.1.0 -m "v0.1.0"`, SHA notieren
  (`git rev-parse "v0.1.0^{commit}"`).
- [ ] **Step 5: Push – erst nach Freigabe durch Christian** – `git push origin main --follow-tags`.

---

### Task 7: Übergabe an docker-netbox-wus

Das Image-Repo wird hier nicht geändert. Es entsteht eine Übergabe in
`~/projects/_handoff/<Verzeichnisname von docker-netbox-wus>/2026-11-18-netbox-sso-redirect.md`
(Verzeichnisname unter `~/projects` vorher prüfen, Ordner bei Bedarf anlegen).

- [ ] **Step 1: Übergabe schreiben** mit:
  - `plugin_requirements.txt`: `git+https://github.com/wus-technik/netbox-sso-redirect@<SHA>  # v0.1.0`
  - Lesetoken nur per BuildKit-Secret und nur für den einen Befehl, ohne Datei im Image:

    ```dockerfile
    RUN --mount=type=secret,id=gh_token \
        GIT_CONFIG_COUNT=1 \
        GIT_CONFIG_KEY_0="http.https://github.com/.extraheader" \
        GIT_CONFIG_VALUE_0="Authorization: Basic $(printf 'x-access-token:%s' "$(cat /run/secrets/gh_token)" | base64 -w0)" \
        /opt/netbox/venv/bin/pip install --no-cache-dir -r /opt/netbox/plugin_requirements.txt
    ```

    Kein `git config --global`, kein `--build-arg`, kein Token in der URL, kein `set -x`.
    Danach das fertige Image prüfen: `grep -r` nach dem Token-Präfix in `/root/.gitconfig`,
    `/opt/netbox/venv/**/direct_url.json` und im Build-Log – erwartet: kein Treffer.
  - `configuration/plugins.py`: Plugin aktivieren; `collectstatic` muss nach der Installation laufen.
  - `SOCIAL_AUTH_LOGIN_ERROR_URL` = `LOGIN_URL` + `?local=1` (mit `BASE_PATH`).
  - `LOGIN_FORM_HIDDEN` bleibt `False`.
  - `LOGOUT_REDIRECT_URL` auf die End-Session-URL von authentik; Landeseite danach nicht `/login/`.
  - Proxy: `X-Forwarded-*` überschreiben, `ALLOWED_HOSTS`/`CSRF_TRUSTED_ORIGINS` prüfen, CSP notieren.
  - Staging-Tests (lokal nicht abgedeckt): Login mit `next`; Fehler bei authentik →
    `/login/?local=1`; Abmelden ohne `id_token_hint` beendet die authentik-Sitzung; lokaler Login
    über `?local=1`; Browser-Konsole ohne CSP-Fehler.
- [ ] **Step 2: In Jira ITSYS-422 kommentieren**, dass das Plugin fertig ist und die Übergabe liegt.
