# Review: Implementation of the plan (2026-11-18)

**Scope:** Execution of `docs/superpowers/plans/2026-11-18-netbox-sso-redirect.md` (Tasks 1–6) on
branch `feature/ITSYS-422-sso-redirect`, range `1ce239f..fe5f7e4`. Ref: ITSYS-422.

**Model/command:** Codex CLI 0.170.0 via the `codex-reviewer` agent,
`codex exec --sandbox read-only --cd <repo> --model <model> …`.
- Task reviews and the scoped re-review: `gpt-6.1-terra`.
- Final whole-branch review: `gpt-6.1-sol`, reasoning effort high. The prompt went in via stdin because the argument list was too long on Windows.

Codex had no Docker access, so test results come from the implementers' runs in the pinned NetBox 4.7.3 container: `$TEST` 46 OK, 2 skipped; `$TEST_BP` 2 OK.

## Task reviews

| Task | Commits | Verdict | Findings | Outcome |
|---|---|---|---|---|
| 1 Test environment | `6c8a1c4` | ❌ → ruled | Important (plan-mandated): `$TEST_BP` target module missing | Sequencing issue; module created and run in Task 4 |
| 2 Settings | `a34e8e4` | approved | – | Backend resolution checked against social-core 5.2.0 and NetBox `AUTHENTICATION_BACKENDS` |
| 3 `next` check | `8a237ce`, `fea2e33` | approved | – | Raw `QUERY_STRING` decoding of all hostile variants verified |
| 4 Middleware + bridge | `fc0d5b5` | approved | ⚠️ middleware order and `MiddlewareNotUsed` rebuild not verified against source | Covered by passing full-stack tests in the 4.7.3 container |
| 5 Script + begin flow | `e883403` | approved | Minor: begin test posts `next` directly; static test checks the source tree, not the wheel | Kept; wheel content checked in Task 6 |
| 6 Release 0.1.0 | `f988698` | approved | – | `package-data` needed and added; recursive globs confirmed |

Deviations from the plan, decided during execution:
- `test_htmx_expired_session_full_navigation` compares the parsed `next` value. Django 6.1.2's `redirect_to_login` encodes with `safe="/"`, so NetBox sends `next=/dcim/devices/`, not `%2F…`.
- `dev/config/plugins.py` reads `BASE_PATH` from the environment (dev only). netbox-docker does not, and `$TEST_BP` would otherwise only skip.
- The API tests use a v1 token, because the dev environment has no `API_TOKEN_PEPPERS`.

## Final whole-branch review (gpt-6.1-sol, high): Ready with fixes

| # | Severity | Location | Finding | Verdict | Done |
|---|---|---|---|---|---|
| 1 | important | `sso-redirect.js:22`, `bridge.html:17` | After a failed automatic start, the button did a native POST. Under CSP `form-action 'self'`, Chromium blocks the redirect to the IdP. Concurrent submits were also possible. | confirmed | `fe5f7e4`: submit is intercepted; one guarded fetch path for the automatic start and manual retries; button disabled while pending |
| 2 | minor | `README.md:105` | README listed the authentik error path as covered locally | confirmed | `fe5f7e4`: error path and logout listed as pending staging checks |

Codex marked all earlier rulings and deferred minors as "keep".

## Scoped re-review of the fix (gpt-6.1-terra)

- Finding 2: addressed.
- Finding 1: addressed for every async failure path (HTTP error, invalid JSON, missing `url`, network error). No automatic retry.
- **New, open (important per Codex):** a synchronous throw in `attempt()` leaves the button disabled, and `preventDefault` blocks the native submit. This happens if `fetch` is missing or `new FormData(form)` throws. The "Lokale Anmeldung" link remains.
  **Status: parked.** Every browser NetBox 4.7 supports has `fetch`/`FormData`, and NetBox's own `initSSOForms()` relies on them. Small follow-up: wrap the synchronous part in `try/catch`, or check for `fetch` before registering the submit handler.

## Manual check (browser, local stack)

- `http://localhost:8000/` → `/login/?next=/` → bridge → `http://localhost:9000/authorize?client_id=netbox-dev&…` (the 404 there is expected). Repeated after the fix with `?next=/dcim/devices/`.
- `/login/?local=1` shows the NetBox form.
- No console errors were captured.
- Not checked in the browser: the page without JavaScript (the button and link are in the HTML per the tests), and the manual retry after a failed start.
