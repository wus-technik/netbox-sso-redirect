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
  `/oauth/begin/<backend>/` (`SocialAuthBeginView`). Ein GET auf `/oauth/login/oidc/` liefert 405,
  eine einfache Umleitung am Reverse-Proxy reicht also nicht.
- Eine überschriebene `templates/login.html` müsste bei jedem NetBox-Update gegen das Original
  abgeglichen werden. Eine Middleware hängt nicht an der Vorlage.

## Geplantes Verhalten

1. **Middleware** (über `PluginConfig.middleware`): GET auf `LOGIN_URL` ohne angemeldeten Nutzer
   und ohne `local=1` liefert eine Mini-Seite, die sofort per POST (mit CSRF-Token und
   übernommenem `next`) an `/oauth/begin/oidc/` schickt. Ohne JavaScript bleibt ein Knopf.
2. **`/login/?local=1`** rendert die normale NetBox-Login-Seite mit Formular.
3. **Kein Login-Kreisel:** `SOCIAL_AUTH_LOGIN_ERROR_URL` zeigt auf `/login/?local=1`; ein Fehler
   bei authentik landet sonst wieder auf `/login/` und startet SSO von vorn.
4. **Abmelden:** `LOGOUT_REDIRECT_URL` auf die End-Session-URL von authentik, sonst meldet die
   noch offene authentik-Sitzung den Nutzer sofort wieder an.
5. **Nicht betroffen:** API-Zugriffe mit Token, `/oauth/*`, statische Dateien, alles außer
   `LOGIN_URL`.

Einstellungen (Vorschlag, in `PLUGINS_CONFIG['netbox_sso_redirect']`): `backend` (Standard
`oidc`), `local_param` (Standard `local`).

## Ausgangslage im Image

- `configuration/extra.py` setzt `SOCIAL_AUTH_PIPELINE` mit `create_user` plus eigene Schritte
  (`custom_pipeline.add_groups`, `remove_groups`, `set_roles`).
- `configuration/authentik.py` setzt `SOCIAL_AUTH_OIDC_*` und `LOGOUT_REDIRECT_URL`
  (aus der Umgebung, Standard `/`).
- Plugins werden in `plugin_requirements.txt` exakt gepinnt und in `configuration/plugins.py`
  aktiviert.

## Entwicklung

Noch offen: Testumgebung (NetBox-Quellbaum oder netbox-docker lokal), Tests, Paketierung und
Einbindung ins Image (aus dem Git-Repo oder als lokaler Pfad im Build-Kontext).
