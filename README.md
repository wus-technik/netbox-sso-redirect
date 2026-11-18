# netbox-sso-redirect

NetBox-Plugin der W&S Technik: Ein nicht angemeldeter Aufruf startet sofort den SSO-Login
(OIDC gegen authentik). Das lokale Login-Formular ist nur noch über `/login/?local=1` erreichbar,
als Notzugang für das lokale Konto `admin`. Mit `local_login = False` ist die Anmeldung mit
Passwort ganz gesperrt und wird nur im Notfall per Konfiguration wieder freigegeben.

Jira: [ITSYS-422](https://wus-technik.atlassian.net/browse/ITSYS-422) · Eingebunden in das Image
`wus-technik/docker-netbox-wus` (Stack 712 `netbox`, docker106).

## Status

Version 0.3.0: Die Umsetzung ist vorhanden und getestet (Middleware, Brückenseite, Prüfung von
`next` und der Einstellungen, Sperre des lokalen Logins). 0.2.0 brachte die Einstellung
`local_login` (Standard `True`, Verhalten wie 0.1.0). 0.3.0 erhält `next` nach einem SSO-Fehler,
baut die Verbindung zum IdP vorab auf und zeigt den Spinner bis zum Seitenwechsel (Punkt 9);
neue Einstellungen gibt es nicht. Das Plugin bringt Template und statische Datei
(`sso-redirect.js`) mit; das Image muss nach der Installation des Plugins `collectstatic` ausführen, sonst fehlt das
Skript der Brückenseite.

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
   Pfade reicht die Middleware unverändert an NetBox durch. HTMX-Anfragen (Header `HX-Request`)
   bekommen statt der Brückenseite eine leere Antwort mit `HX-Redirect` auf dieselbe URL, damit
   der Browser ganz neu navigiert, statt die Seite als Fragment einzusetzen.
2. **Brückenseite:** Sie enthält ein Formular mit dem CSRF-Token aus `get_token(request)` (das
   Cookie ist `HttpOnly`) und `next` als verstecktem, HTML-escaptem POST-Feld. Ziel ist
   `reverse('social_auth_begin', args=[backend])`, also NetBox' eigener Wrapper, nicht
   `social:begin`. Das Skript schickt das wie NetBox' `initSSOForms()` per `fetch` mit
   `Accept: application/json` ab und folgt der zurückgegebenen `url` per `location.assign()`.
   Grund: Chromium prüft eine CSP `form-action` an jeder Station der Weiterleitungskette, ein
   klassischer Form-POST würde dann still scheitern. Ohne JavaScript bleibt das Formular mit
   Knopf. Das Skript liegt als statische Datei des Plugins vor, nicht inline.
   Antwort-Header: `Cache-Control: no-store, private`, `X-Frame-Options: DENY`. Die Seite erbt
   wie NetBox' `login.html` von `base/base.html` (Logo, Farbmodus, `BANNER_LOGIN`, Meldungen)
   und bindet das Skript mit der Plugin-Version in der URL ein (`?v=<version>`), damit nach
   einem Update kein altes Skript aus dem Browser-Cache läuft. Das Formular trägt bewusst nicht
   die Klasse `sso-login-form`, sonst würde NetBox' `initSSOForms()` es zusätzlich übernehmen.
3. **`next` wird geprüft:** `url_has_allowed_host_and_scheme(next, {request.get_host()},
   require_https=request.is_secure())`. Ein ungültiger oder fehlender Wert wird durch
   `settings.LOGIN_REDIRECT_URL` ersetzt. Andere Query-Parameter werden nicht übernommen.
4. **`/login/?local=1`** rendert die normale NetBox-Login-Seite mit Formular. Das setzt
   `LOGIN_FORM_HIDDEN = False` voraus (Standard).
5. **POST auf `/login/`** bleibt bei `local_login = True` unangetastet, auch ohne `local=1`.
   `?local=1` soll nur verhindern, dass man versehentlich auf dem Formular landet; eine
   Sicherheitsgrenze ist es nicht. Die Grenze ist `local_login = False` (Punkt 8).
6. **Nicht betroffen:** API-Zugriffe mit Token, `/oauth/*`, statische Dateien, alles außer
   `LOGIN_URL`. Ausnahme bei `local_login = False`: `POST /api/users/tokens/provision/` (Punkt 8).
7. **Einstellungen** in `PLUGINS_CONFIG['netbox_sso_redirect']`: `backend` (Standard `oidc`),
   `local_param` (Standard `local`), `local_login` (Standard `True`). `backend` und
   `local_param` werden beim Start geprüft: nicht leer, `local_param` nicht `next`, das Backend
   ist in `AUTHENTICATION_BACKENDS` bzw. `REMOTE_AUTH_BACKEND` eingetragen. Bei ungültiger
   Konfiguration leitet das Plugin nicht um und schreibt eine Warnung ins Log; der normale
   Login bleibt erreichbar. Eine gesetzte Sperre (Punkt 8) bleibt davon unberührt.
8. **`local_login = False` sperrt die Anmeldung mit Passwort.** In der Standardkonfiguration
   von NetBox 4.7.3 gibt es zwei anonyme Einstiegspunkte, an denen Benutzername und Passwort
   geprüft werden: `LoginView` (URL-Name `login`) und `POST /api/users/tokens/provision/`, das
   gegen Benutzername und Passwort ein API-Token ausstellt. Die Middleware löst den Pfad auf
   (`resolve(request.path_info)`) und beantwortet jeden POST auf eine dieser Views mit 403 (Text bzw. JSON,
   Warnung mit Pfad und Client-Adresse im Log), unabhängig von `local=1` und vom
   Anmeldestatus. `?local=1` zeigt dann kein Formular, sondern die Brückenseite ohne
   automatischen Start und ohne Link „Lokale Anmeldung“: Dorthin führt auch ein SSO-Fehler
   (`SOCIAL_AUTH_LOGIN_ERROR_URL`), ein Autostart würde eine Schleife erzeugen. Meldungen von
   social-auth zeigt die Brückenseite an. Nicht betroffen: SSO, API-Tokens, bestehende
   Sitzungen. Nur das Bool `True` gibt den Login frei; jeder andere Wert (auch der String
   `"true"`) sperrt und schreibt eine Warnung, damit ein Tippfehler die Sperre nicht öffnet.
   Zusätzlich aktivierte Wege mit Passwort (Django-Admin, Basic-Auth, weitere Backends) deckt
   die Sperre nicht ab. **Notfall** (authentik nicht erreichbar): `local_login` auf `True` setzen, NetBox neu
   starten, über `/login/?local=1` mit dem Notfallkonto anmelden, danach wieder sperren.
9. **Nach einem SSO-Fehler und beim Warten** (seit 0.3.0):
   - **`next` bleibt erhalten.** social-core legt `next` beim Start in der Session ab, leitet bei
     einem Fehler aber auf `SOCIAL_AUTH_LOGIN_ERROR_URL` ohne `next` um. Ein anonymer GET auf
     `LOGIN_URL?local=1` ohne `next` wird deshalb einmal auf dieselbe URL mit dem `next` aus der
     Session umgeleitet (302, `no-store`), sofern es die Prüfung aus Punkt 3 besteht. Ein `next` in
     der URL hat Vorrang; HTMX-Anfragen werden nicht umgeleitet. Gilt in beiden Modi von
     `local_login`; am Image ändert sich nichts. social-core überschreibt `next` in der Session
     nur, wenn ein Start `next` mitschickt; ein älterer Wert kann also stehen bleiben. Er besteht
     trotzdem die Prüfung aus Punkt 3, schlimmstenfalls landet man auf einer anderen Seite
     desselben Hosts.
   - **Eine Meldung.** Nach einem Abbruch bei authentik zeigt NetBox genau einen Toast („Single
     Sign-On ist fehlgeschlagen …“). NetBox' `login.html` enthält zusätzlich den versteckten
     Block `#sso-error` („… kann nicht gestartet werden …“, `d-none`); den liest eine
     Textauslese mit, sichtbar ist er nicht. Bei gesperrtem lokalem Login fehlt er ganz.
   - **Preconnect:** Die Brückenseite setzt `<link rel="preconnect">` und `dns-prefetch` auf den
     Ursprung aus `SOCIAL_AUTH_<BACKEND>_OIDC_ENDPOINT` (für `oidc`:
     `SOCIAL_AUTH_OIDC_OIDC_ENDPOINT`), nur bei `http`/`https`, gebaut aus Host und Port (ohne
     Zugangsdaten). Fehlt die Einstellung oder ist sie ungültig, entfällt er.
   - **Spinner bis zum Seitenwechsel**, auch beim Klick auf den Knopf. Kommt die Seite aus dem
     Back-Forward-Cache zurück (Zurück vom IdP, v. a. iOS Safari), werden Spinner und Knopf
     zurückgesetzt, ohne erneuten Autostart.
   - Weiterhin kein Inline-Style und kein Inline-Skript des Plugins (`style-src 'self'` bleibt
     möglich; die Inline-Skripte von NetBox' `base.html` betreffen `script-src`).

Im Image, nicht im Plugin (Aufgabe für `docker-netbox-wus`):

- **Kein Login-Kreisel:** `SOCIAL_AUTH_LOGIN_ERROR_URL` auf `LOGIN_URL` + `?local=1` (mit
  `BASE_PATH`). NetBox setzt den Wert standardmäßig auf `LOGIN_URL`; die Konfiguration wird
  danach geladen und überschreibt ihn.
- **`LOGIN_FORM_HIDDEN`** bleibt `False`, sonst zeigt auch `?local=1` kein Formular.
- **`local_login`** kommt aus einer Umgebungsvariable des Stacks (Standard: gesperrt), damit der
  Notzugang ohne neues Image freigeschaltet werden kann. Der Wert wird in `plugins.py` explizit
  in ein Bool übersetzt.
- **Konten mit Passwort:** Nur das Notfallkonto behält ein nutzbares Passwort; per SSO
  angelegte Konten haben keins.
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
  Für eine Vorschau im Browser: `docker compose -f dev/docker-compose.yml run -d --name sso-preview
  --service-ports [-e SSO_LOCAL_LOGIN=false] netbox`, danach im Container `manage.py
  collectstatic --no-input`; die Seite liegt unter `http://localhost:8000/login/`.
- **Tests:** netbox-docker lokal (Docker Desktop), Image NetBox 4.7.3 per Digest gepinnt, mit
  PostgreSQL und Redis. Das Plugin wird in den Container gemountet; die Tests laufen dort mit
  `manage.py test netbox_sso_redirect` gegen das echte NetBox. Abgedeckt werden mindestens:
  Brückenseite und Header nach dem kompletten Middleware-Stack, `next`-Fälle (`//evil`,
  `/\evil`, `%2F%2F`, doppelt kodiert, `http://` unter HTTPS, leer, mehrfach), `local=1` und
  Varianten (`local=0`, `local=`), `BASE_PATH`, API-Token, HTMX-Anfragen, HEAD, angemeldeter
  Nutzer, ungültige Plugin-Einstellungen, Sperre des lokalen Logins (Formular-POST und
  Token-Provisioning mit gültigem Passwort, auch unter `BASE_PATH`; SSO-Start, Token und
  Sitzung weiter möglich; Wert, der kein Bool ist). Der Fehlerpfad von authentik und der Logout sind lokal
  nicht abgedeckt und stehen als Prüfungen gegen das Staging aus.
- **Einbindung ins Image:** in `plugin_requirements.txt` auf den **Commit-SHA** gepinnt
  (Tag nur als Kommentar), z. B.
  `git+https://github.com/wus-technik/netbox-sso-redirect@<sha>  # v0.2.0`. Das Repo ist
  privat; der Lesetoken kommt ausschließlich über ein BuildKit-`--secret`-Mount in denselben
  `RUN`-Schritt, nie über `--build-arg` oder die URL, damit er nicht in Layern, Logs oder im
  pip-Cache landet.
- **NetBox-Update:** `max_version = "4.7.99"` sperrt das Plugin für 4.8 bewusst. Beim Update
  von NetBox wird das Plugin gegen die neue Version getestet und die Grenze angehoben.
- `__version__` bleibt ein Literal, weil `pyproject.toml` die Version per `attr` liest.
