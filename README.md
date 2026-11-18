# netbox-sso-redirect

NetBox-Plugin der W&S Technik: Ein nicht angemeldeter Aufruf startet sofort den SSO-Login
(OIDC gegen authentik). Das lokale Login-Formular ist nur noch über `/login/?local=1` erreichbar,
als Notzugang für das lokale Konto `admin`.

Jira: [ITSYS-422](https://wus-technik.atlassian.net/browse/ITSYS-422) · Eingebunden in das Image
`wus-technik/docker-netbox-wus` (Stack 712 `netbox`, docker106).

## Warum ein Plugin

NetBox 4.7 bringt das nicht mit (geprüft am laufenden 4.7.3-Container, 18.11.2026):

- `LOGIN_FORM_HIDDEN = True` blendet das Formular nur im Template aus. `LoginView.post()` prüft
  die Einstellung nicht, ein POST mit Benutzername und Passwort auf `/login/` funktioniert weiter.
- Eine automatische Weiterleitung gibt es nicht.
- Seit social-auth-app-django 6 startet der SSO-Login per **POST mit CSRF-Token** auf
  `/oauth/begin/<backend>/` (NetBox' `SocialAuthBeginView`, URL-Name `social_auth_begin`). Auch
  die social-django-Route `/oauth/login/<backend>/` (`social:begin`) liefert auf GET 405. Eine
  einfache Umleitung am Reverse-Proxy reicht also nicht.
- Eine überschriebene `templates/login.html` müsste bei jedem NetBox-Update gegen das Original
  abgeglichen werden. Eine Middleware hängt nicht an der Vorlage.

## Geplantes Verhalten

1. **Middleware** (über `PluginConfig.middleware`, läuft nach `AuthenticationMiddleware` und
   `CsrfViewMiddleware`): Ein **GET** auf `settings.LOGIN_URL` (Vergleich mit `request.path`,
   `BASE_PATH` ist darin enthalten) ohne angemeldeten Nutzer liefert eine Brückenseite, sofern
   der Query-Parameter nicht genau `local=1` ist. Angemeldete Nutzer, HEAD, POST und alle anderen
   Pfade reicht die Middleware unverändert an NetBox durch.
2. **Brückenseite:** Sie enthält ein Formular mit dem CSRF-Token aus `get_token(request)` (das
   Cookie ist `HttpOnly`) und `next` als verstecktem, HTML-escaptem POST-Feld. Ziel ist
   `reverse('social_auth_begin', args=[backend])`, also NetBox' eigener Wrapper, nicht
   `social:begin`. Das Skript schickt das wie NetBox' `initSSOForms()` per `fetch` mit
   `Accept: application/json` ab und folgt der zurückgegebenen `url` per `location.assign()`.
   Grund: Chromium prüft eine CSP `form-action` an jeder Station der Weiterleitungskette, ein
   klassischer Form-POST würde dann still scheitern. Ohne JavaScript bleibt das Formular mit
   Knopf. Das Skript liegt als statische Datei des Plugins vor, nicht inline.
   Antwort-Header: `Cache-Control: no-store, private`, `X-Frame-Options: DENY`.
3. **`next` wird geprüft:** `url_has_allowed_host_and_scheme(next, {request.get_host()},
   require_https=request.is_secure())`. Ein ungültiger oder fehlender Wert wird durch
   `settings.LOGIN_REDIRECT_URL` ersetzt. Andere Query-Parameter werden nicht übernommen.
4. **`/login/?local=1`** rendert die normale NetBox-Login-Seite mit Formular. Das setzt
   `LOGIN_FORM_HIDDEN = False` voraus (Standard).
5. **POST auf `/login/` bleibt unangetastet**, auch ohne `local=1`. `?local=1` soll nur
   verhindern, dass man versehentlich auf dem Formular landet; eine Sicherheitsgrenze ist es
   nicht. Das lokale Konto `admin` braucht deshalb ein starkes Passwort.
6. **Nicht betroffen:** API-Zugriffe mit Token, `/oauth/*`, statische Dateien, alles außer
   `LOGIN_URL`.
7. **Einstellungen** in `PLUGINS_CONFIG['netbox_sso_redirect']`: `backend` (Standard `oidc`),
   `local_param` (Standard `local`). Sie werden beim Start geprüft: nicht leer, `local_param`
   nicht `next`, das Backend ist in `AUTHENTICATION_BACKENDS` bzw. `REMOTE_AUTH_BACKEND`
   eingetragen. Bei ungültiger Konfiguration leitet das Plugin nicht um und schreibt eine
   Warnung ins Log; der normale Login bleibt erreichbar.

Im Image, nicht im Plugin (Aufgabe für `docker-netbox-wus`):

- **Kein Login-Kreisel:** `SOCIAL_AUTH_LOGIN_ERROR_URL` auf `LOGIN_URL` + `?local=1` (mit
  `BASE_PATH`). NetBox setzt den Wert standardmäßig auf `LOGIN_URL`; die Konfiguration wird
  danach geladen und überschreibt ihn.
- **`LOGIN_FORM_HIDDEN`** bleibt `False`, sonst zeigt auch `?local=1` kein Formular.
- **Abmelden:** NetBox leitet nach dem Logout nur auf `LOGOUT_REDIRECT_URL` um und baut keinen
  OIDC-Logout. Der Wert zeigt auf die End-Session-URL von authentik; die Seite danach darf nicht
  `/login/` ohne `local=1` sein, sonst startet SSO sofort neu. Ob authentik ohne
  `id_token_hint` die Sitzung beendet, wird im Ende-zu-Ende-Test geprüft.
- **Proxy:** überschreibt `X-Forwarded-Host`/`-Proto` (NetBox vertraut ihnen),
  `ALLOWED_HOSTS` und `CSRF_TRUSTED_ORIGINS` passen zum öffentlichen Ursprung. Die
  tatsächliche CSP des Proxys wird vor dem Rollout festgehalten.

## Ausgangslage im Image

- `configuration/extra.py` setzt `SOCIAL_AUTH_PIPELINE` mit `create_user` plus eigene Schritte
  (`custom_pipeline.add_groups`, `remove_groups`, `set_roles`).
- `configuration/authentik.py` setzt `SOCIAL_AUTH_OIDC_*` und `LOGOUT_REDIRECT_URL`
  (aus der Umgebung, Standard `/`).
- Plugins werden in `plugin_requirements.txt` exakt gepinnt und in `configuration/plugins.py`
  aktiviert.

## Entwicklung

- **Testumgebung:** `dev/docker-compose.yml` (NetBox-Image `netboxcommunity/netbox:v4.7.3`, Digest
  `sha256:22cf3c61fc367fb74a5cf6de018e9d7e10a7da8d09a695eab30740793040de08`). Das Plugin wird per
  `PYTHONPATH=/opt/plugin` eingebunden, nicht installiert. Unter Git Bash auf Windows vor den
  Befehlen `export MSYS_NO_PATHCONV=1` setzen (sonst wird `/opt/...` umgeschrieben). Der erste
  Lauf migriert die Datenbank und dauert einige Minuten.
  ```bash
  docker compose -f dev/docker-compose.yml up -d postgres redis idp
  # $TEST
  docker compose -f dev/docker-compose.yml run --rm netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect --keepdb -v 2
  # $TEST_BP
  docker compose -f dev/docker-compose.yml run --rm -e BASE_PATH=netbox/ netbox /opt/netbox/venv/bin/python /opt/netbox/netbox/manage.py test netbox_sso_redirect.tests.test_base_path --keepdb -v 2
  ```
- **Tests:** netbox-docker lokal (Docker Desktop), Image NetBox 4.7.3 per Digest gepinnt, mit
  PostgreSQL und Redis. Das Plugin wird in den Container gemountet; die Tests laufen dort mit
  `manage.py test netbox_sso_redirect` gegen das echte NetBox. Abgedeckt werden mindestens:
  Brückenseite und Header nach dem kompletten Middleware-Stack, `next`-Fälle (`//evil`,
  `/\evil`, `%2F%2F`, doppelt kodiert, `http://` unter HTTPS, leer, mehrfach), `local=1` und
  Varianten (`local=0`, `local=`), `BASE_PATH`, API-Token, HTMX-Anfragen, HEAD, angemeldeter
  Nutzer, ungültige Plugin-Einstellungen, Fehlerpfad von authentik.
- **Einbindung ins Image:** in `plugin_requirements.txt` auf den **Commit-SHA** gepinnt
  (Tag nur als Kommentar), z. B.
  `git+https://github.com/wus-technik/netbox-sso-redirect@<sha>  # v0.1.0`. Das Repo ist
  privat; der Lesetoken kommt ausschließlich über ein BuildKit-`--secret`-Mount in denselben
  `RUN`-Schritt, nie über `--build-arg` oder die URL, damit er nicht in Layern, Logs oder im
  pip-Cache landet.
- **NetBox-Update:** `max_version = "4.7.99"` sperrt das Plugin für 4.8 bewusst. Beim Update
  von NetBox wird das Plugin gegen die neue Version getestet und die Grenze angehoben.
- `__version__` bleibt ein Literal, weil `pyproject.toml` die Version per `attr` liest.
