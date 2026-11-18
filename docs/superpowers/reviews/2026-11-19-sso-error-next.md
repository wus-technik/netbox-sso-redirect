# Review: `next` nach SSO-Fehler, Preconnect, Spinner (0.3.0, 2026-11-19)

**Umfang:** Version 0.3.0, Branch `feature/ITSYS-422-sso-error-next`, Commits `cc77589..754a088`, dazu
die Korrekturen aus diesem Review. Anlass ist die Rückmeldung aus dem Staging-Test von
docker-netbox-wus. Ref: ITSYS-422.

**Modell/Befehl:** Codex CLI 0.170.0 über den Agenten `codex-reviewer`, `codex exec --sandbox
read-only --cd <repo> --model gpt-6.1-sol -c model_reasoning_effort=high - < <prompt>` (Prompt per
stdin). Codex hat social-core 5.2.0, social-app-django 6.1.0 und NetBox 4.7.3 aus den gepinnten
Quellen gelesen, aber kein Docker gehabt. Die Tests liefen im NetBox-4.7.3-Container: `$TEST` 81 OK,
4 übersprungen; `$TEST_BP` 4 OK.

**Ergebnis:** APPROVE. Codex hat keinen kritischen, hohen oder mittleren Befund gemeldet.

| # | Schwere | Ort | Befund | Urteil | Umgesetzt |
|---|---|---|---|---|---|
| 1 | gering | `conf.py` `get_idp_origin` | Ein fehlerhafter Endpunkt (z. B. `https://[idp.example/x`) führt bei `urlsplit` zu einem `ValueError`, die Brückenseite antwortet dann mit 500. | gültig | `try/except ValueError` (auch für einen ungültigen Port) → kein Preconnect; Tests |
| 2 | gering | `conf.py` `get_idp_origin` | Der Ursprung wurde aus `netloc` gebaut; Zugangsdaten (`user:pw@`) aus der Endpunkt-URL wären im HTML gelandet. (Beobachtung des Agenten) | gültig | Ursprung aus `hostname` und `port`, IPv6 in Klammern; Tests |
| 3 | gering | `tests/test_base_path.py` | Die Wiederherstellung von `next` war unter `BASE_PATH` nicht getestet. | gültig | `test_restore_next_with_prefix` |
| 4 | gering | `tests/test_sso_error.py` | Der Docstring sprach von einem „gültigen state“; social-core wertet `error` aber vor dem state aus. | gültig | Docstring präzisiert; der Test läuft weiter über den echten Fehlerweg |

**Von Codex bestätigt:**
- Den Schlüssel `session["next"]` setzt `do_auth`; der Fehlerweg (`SocialAuthExceptionMiddleware`) lässt die Session unverändert.
- Kein offener Redirect, keine Schleife, die 302-Antwort ist `no-store`, Parameter bleiben erhalten.
- Kein `crossorigin` nötig; das Escaping im Template genügt.
- Nach einer Rückkehr aus dem Back-Forward-Cache startet der Login nicht erneut automatisch.
- Das README stimmt mit dem Code überein.

**Restrisiko, festgehalten im README:** Ein älterer Wert für `next` kann in der Session stehen bleiben, wenn ein späterer Start kein `next` mitschickt. Der Wert wird trotzdem geprüft; schlimmstenfalls landet man auf einer anderen Seite desselben Hosts.

## Manuelle Prüfung (Browser, lokaler Stack)

Callback `/oauth/complete/oidc/?error=access_denied&state=<aktuell>` nach einem Start von `/dcim/devices/` aus:

- **Gesperrter lokaler Login:**
  - Ziel ist `/login/?local=1&next=%2Fdcim%2Fdevices%2F`.
  - Brückenseite ohne Autostart, `next` steht im Formular.
  - Genau ein Toast: „Single Sign-On ist fehlgeschlagen …“.
- **Freigegebener lokaler Login:**
  - Gleiches Ziel, NetBox' Formular mit `next`.
  - Ein sichtbarer Toast.
  - Der zweite Text aus dem Staging-Bericht („… kann nicht gestartet werden“) ist NetBox' versteckter Block `#sso-error` (`d-none`) in `login.html`, keine zweite Meldung.
