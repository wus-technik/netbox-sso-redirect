# Review: Sperre des lokalen Logins und Brückenseite im NetBox-Layout (2026-11-18)

**Umfang:** Version 0.2.0, Branch `feature/ITSYS-422-local-login-switch`, Bereich `4613e33..` (Einstellung
`local_login`, Sperre von `POST /login/` und `POST /api/users/tokens/provision/`, Brückenseite auf
Basis von `base/base.html`). Ref: ITSYS-422.

**Modell/Befehl:** Codex CLI 0.170.0 über den Agenten `codex-reviewer`,
`codex exec --sandbox read-only --cd <repo> --model <modell> - < <prompt>` (Prompt per stdin).
- Erstes Review von `4613e33..f198b38`: `gpt-6.1-sol`, Reasoning high. Gegengelesen gegen NetBox v4.7.3,
  Django 6.1.2 und DRF von upstream.
- Gezielte Nachprüfung von `f198b38..cd02b9f`: `gpt-6.1-terra`.

Codex hatte kein Docker. Testergebnisse stammen aus dem gepinnten NetBox-4.7.3-Container: `$TEST` 64 OK,
3 übersprungen; `$TEST_BP` 3 OK.

## Erstes Review (gpt-6.1-sol): CHANGES_REQUESTED

| # | Schwere | Ort | Befund | Urteil | Umgesetzt |
|---|---|---|---|---|---|
| 1 | wichtig | `middleware.py` `_blocks_password_login` | Die Sperre verglich `request.path` mit `LOGIN_URL`. Bei einem WSGI-Mount (`SCRIPT_NAME`) oder einer `LOGIN_URL` mit Query erreichte ein POST mit gültigem Passwort trotzdem `LoginView`. In der Standardkonfiguration nicht erreichbar, weil NetBox `LOGIN_URL` fest setzt. | wahrscheinlich gültig | `cd02b9f`: Erkennung über `resolve(request.path_info).view_name` (`login`, `users-api:token_provision`); Test mit `SCRIPT_NAME` |
| 2 | gering | `tests/test_local_login.py` `test_sso_begin_still_works` | Prüfte nur `!= 403` und hätte auch 400 oder 500 akzeptiert. | gültig | `cd02b9f`: OIDC-Discovery gemockt; geprüft werden 200 und die IdP-URL |
| 3 | gering | `README.md` Punkte 6 und 8 | Punkt 6 widersprach der Sperre. „genau zwei Stellen“ war zu absolut: `/user/password/` prüft ebenfalls ein Passwort, setzt aber eine Sitzung voraus. | gültig | `cd02b9f`: Ausnahme in Punkt 6; Punkt 8 auf die anonymen Einstiegspunkte der Standardkonfiguration begrenzt; nicht abgedeckte Wege genannt |

Ohne Befund von Codex geprüft:
- **Weitere Wege mit Passwort:** keine Basic-Auth in DRF, GraphQL nur mit Sitzung oder Token, kein Django-Admin.
- **Methoden und Pfadvarianten:** HEAD, PUT, Method-Override, `/login` ohne Schrägstrich, doppelte Schrägstriche und Prozentkodierung führen nicht an der Sperre vorbei.
- **Verhalten bei Fehlkonfiguration:** Die Sperre bleibt zu.
- **XSS:** keine Lücke in Template und Skript.

## Gezielte Nachprüfung (gpt-6.1-terra)

- Befunde 1–3: ADDRESSED.
- **Neu, gering** (Codex: mittel). Ort: `middleware.py` `_view_name`. Befund: `resolve()` ignorierte ein von einer früheren Middleware gesetztes `request.urlconf`. Gilt nur, wenn eine Middleware vor dem Plugin eine eigene URL-Konfiguration setzt; NetBox 4.7.3 tut das nicht. Umgesetzt: Danach als Härtung übernommen, `resolve(..., urlconf=getattr(request, "urlconf", None))`.
- **Ohne Befund:**
  - Kontext der Vorlage (`config`, `settings`, `request` über die Context-Processors)
  - Inline-Skripte und CSRF in `base.html`
  - `static_with_params`
  - das Formular ohne die Klasse `sso-login-form`
  - die Fehlerbehandlung im Skript
  - die Dev-Konfiguration

## Manuelle Prüfung (Browser, lokaler Stack)

- **Gesperrt** (`SSO_LOCAL_LOGIN=false`), `/login/?local=1`: Karte im NetBox-Layout, kein Autostart, kein Link „Lokale Anmeldung“.
- **IdP angehalten**, Klick auf „Mit SSO anmelden“: Der Fehlerhinweis erscheint, der Knopf wird wieder aktiv.
- **Freigegeben:** Spinner „Weiterleitung zur SSO-Anmeldung …“ und Link „Lokale Anmeldung“. Keine Konsolenfehler.
- **Dabei gefunden:** Das Skript war ohne Version eingebunden. Chrome nahm deshalb die gecachte Version 0.1.0 und startete trotz `data-autostart="false"`. Nach einem Update wäre das auch im Betrieb passiert und hätte nach einem SSO-Fehler eine Schleife erzeugt. Behoben in `cd02b9f` mit `?v=<plugin_version>` in der Skript-URL; ein Test prüft das.
