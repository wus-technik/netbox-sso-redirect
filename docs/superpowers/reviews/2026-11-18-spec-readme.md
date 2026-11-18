# Review: Spec in README.md (2026-11-18)

**Umfang:** `README.md` als Spec (Stand mit den Entscheidungen zu POST, `next`, Tests,
Einbindung), dazu `pyproject.toml` und `netbox_sso_redirect/__init__.py` (nur Grundgerüst).
Ref: ITSYS-422.

**Modell/Befehl:** Codex CLI 0.170.0, Modell `gpt-6.1-terra`, Reasoning medium,
`codex exec --sandbox read-only --cd <repo> --model gpt-6.1-terra ...`. Codex hat die Quellen
von NetBox v4.7.3 gelesen (`settings.py`, `account/views.py`, `urls.py`, `middleware.py`,
`login.html`); die NetBox-Aussagen wurden gegen dieselben Dateien nachgeprüft. Die Quellen von
social-core/social-app-django und das Verhalten von authentik wurden nicht geprüft.

**Ergebnis:** CHANGES_REQUESTED – keine Fehler im Grundansatz, aber Lücken in der Spec.
Alle Punkte wurden in die README übernommen.

| # | Schwere | Ort | Befund | Urteil | Umgesetzt |
|---|---|---|---|---|---|
| 1 | hoch | README, Verhalten 1 | Klassischer Form-POST scheitert unter CSP `form-action 'self'` (Chromium prüft jede Station der Weiterleitung, NetBox `SocialAuthBeginView` dokumentiert das); Inline-Skript kann an `script-src` scheitern | bestätigt | Brückenseite nutzt `fetch` mit `Accept: application/json` + `location.assign`, Skript als statische Datei, Form mit Knopf als Rückfall; CSP des Proxys vor Rollout festhalten |
| 2 | hoch | README, Verhalten 1/2 | `next` muss als POST-Feld an die Begin-View; Prüfung und Rückfallziel unpräzise (`/` statt `LOGIN_REDIRECT_URL`) | bestätigt (NetBox), wahrscheinlich (social-core) | `next` als verstecktes, escaptes Feld; `url_has_allowed_host_and_scheme` mit `require_https`; Rückfall `LOGIN_REDIRECT_URL`; Testfälle aufgezählt |
| 3 | hoch | README, Verhalten 1 | CSRF-Cookie ist `HttpOnly`, Token muss gerendert werden; keine Cache-/Framing-Header definiert | bestätigt | `get_token()` ins Formular; `Cache-Control: no-store, private`, `X-Frame-Options: DENY`; Header-Test nach komplettem Stack |
| 4 | mittel (Codex: hoch) | README, Im Image | `?local=1` zeigt das Formular nur bei `LOGIN_FORM_HIDDEN = False` | bestätigt | als Voraussetzung im Plugin- und Image-Abschnitt |
| 5 | mittel | README, Warum ein Plugin / Verhalten 1 | `social_auth_begin` (NetBox) und `social:begin` (social-django) vermischt; fester Pfad ignoriert `BASE_PATH` | bestätigt | `reverse('social_auth_begin', args=[backend])`; Text getrennt |
| 6 | mittel | README, Verhalten 1 | HEAD sollte kein SSO starten und kein Token erzeugen | teilweise | nur GET; HEAD geht unverändert an NetBox (ersetzt die eigene Festlegung „GET oder HEAD“). Korrektur aus dem Plan-Review: NetBox' eigene Login-Seite setzt auf HEAD ebenfalls ein CSRF-Cookie; das Plugin vermeidet nur, selbst eines zu erzeugen |
| 7 | mittel | README, Im Image | Login-Kreisel: Override mit `BASE_PATH`; Plugin-Einstellungen nicht validiert | bestätigt | Hinweis zu `BASE_PATH`; Einstellungen werden beim Start geprüft, bei Fehler keine Umleitung + Log-Warnung |
| 8 | mittel | README, Im Image | Logout ohne `id_token_hint`; Landeseite darf nicht `/login/` sein | NetBox bestätigt, authentik offen | Landeseite-Regel aufgenommen; authentik-Verhalten im Ende-zu-Ende-Test |
| 9 | niedrig (Codex: mittel) | README, Verhalten 1 | Vergleich mit `LOGIN_URL`, angemeldete Nutzer, `local`-Varianten, andere Query-Parameter undefiniert | bestätigt | je ein Satz + Tests |
| 10 | mittel | README, Entwicklung | Tag ist verschiebbar; Token kann in Layer/Logs landen | bestätigt | Pin auf Commit-SHA, Token nur per BuildKit-`--secret` |
| 11 | mittel | README, Entwicklung | Testaufbau zu vage | bestätigt | Image per Digest, PostgreSQL/Redis, `manage.py test`, Testmatrix |
| 12 | niedrig (Codex: mittel) | README, Verhalten 2 | `get_host()`/`is_secure()` hängen am Proxy (`USE_X_FORWARDED_HOST`) | bestätigt | Proxy-Voraussetzungen im Image-Abschnitt |
| 13 | niedrig | `netbox_sso_redirect/__init__.py:14` | `max_version = "4.7.99"` sperrt 4.8 | bewusst | als Schritt beim NetBox-Update dokumentiert |
| 14 | niedrig | `pyproject.toml:15` | dynamische Version per `attr` bricht bei berechnetem Wert | kein aktueller Fehler | Literal beibehalten, dokumentiert |

**Bestätigt ohne Änderung:** `PluginConfig.middleware` wird hinten an `MIDDLEWARE` angehängt,
`request.user` ist verfügbar; `LoginView.post()` prüft `LOGIN_FORM_HIDDEN` nicht; der
ungesperrte POST auf `/login/` ist als Designentscheidung akzeptiert (starkes Passwort für
`admin`).
