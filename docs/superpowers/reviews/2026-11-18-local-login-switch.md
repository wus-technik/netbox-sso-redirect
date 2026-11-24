# Review: local login block and bridge using the NetBox layout (2026-11-18)

**Scope:** Version 0.2.0, branch `feature/ITSYS-422-local-login-switch`, range
`4613e33..`: `local_login`, blocking `POST /login/` and
`POST /api/users/tokens/provision/`, and the bridge based on `base/base.html`.
Ref: ITSYS-422.

**Model/command:** Codex CLI 0.170.0 via the `codex-reviewer` agent,
`codex exec --sandbox read-only --cd <repo> --model <model> - < <prompt>` (stdin).

- Initial review of `4613e33..f198b38`: `gpt-6.1-sol`, high reasoning.
  Cross-checked against NetBox v4.7.3, Django 6.1.2, and upstream DRF.
- Scoped re-review of `f198b38..cd02b9f`: `gpt-6.1-terra`.

Codex had no Docker access. Tests ran in the pinned NetBox 4.7.3 container:
`$TEST` 64 OK, three skipped; `$TEST_BP` three OK.

## Initial review (gpt-6.1-sol): CHANGES_REQUESTED

| # | Severity | Location | Finding | Verdict | Resolution |
|---|---|---|---|---|---|
| 1 | important | `middleware.py` `_blocks_password_login` | The block compared `request.path` with `LOGIN_URL`. A WSGI mount (`SCRIPT_NAME`) or a query in `LOGIN_URL` allowed a valid-password POST to reach `LoginView`. Not reachable in standard NetBox configuration because NetBox fixes `LOGIN_URL`. | likely valid | `cd02b9f`: identify views through `resolve(request.path_info).view_name` (`login`, `users-api:token_provision`); test with `SCRIPT_NAME` |
| 2 | low | `tests/test_local_login.py` `test_sso_begin_still_works` | Only asserted `!= 403`, which also accepted 400 or 500. | valid | `cd02b9f`: mock OIDC discovery and assert 200 plus the IdP URL |
| 3 | low | README items 6 and 8 | Item 6 contradicted the block. "Exactly two places" was too absolute: `/user/password/` also checks a password but requires a session. | valid | `cd02b9f`: add the exception to item 6; limit item 8 to standard anonymous entry points and identify uncovered routes |

Checked without findings:

- **Other password paths:** no DRF Basic Auth, GraphQL requires a session or token, no Django admin.
- **Methods and path variants:** HEAD, PUT, method override, `/login` without a trailing
  slash, double slashes, and percent encoding do not bypass the block.
- **Misconfiguration:** the block remains closed.
- **XSS:** no vulnerability in the template or script.

## Scoped re-review (gpt-6.1-terra)

- Findings 1–3: ADDRESSED.
- **New, low** (Codex: moderate), `middleware.py` `_view_name`: `resolve()` ignored
  `request.urlconf` set by earlier middleware. Applies only when middleware before
  the plugin sets a custom URL configuration; NetBox 4.7.3 does not.
  Subsequently hardened with `resolve(..., urlconf=getattr(request, "urlconf", None))`.
- No findings for template context (`config`, `settings`, `request` through context
  processors), inline scripts and CSRF in `base.html`, `static_with_params`, omitting
  the `sso-login-form` class, script error handling, or development configuration.

## Manual check (browser, local stack)

- **Blocked** (`SSO_LOCAL_LOGIN=false`), `/login/?local=1`: card in the NetBox layout,
  no auto-start or "Local login" link.
- **IdP stopped**, click "Sign in with SSO": error shown, button re-enabled.
- **Allowed:** "Redirecting to SSO sign-in …" spinner and "Local login" link; no console errors.
- **Additional finding:** the script URL lacked a version. Chrome reused cached 0.1.0
  and auto-started despite `data-autostart="false"`. In production, an update could
  therefore cause a loop after an SSO error. Fixed in `cd02b9f` with
  `?v=<plugin_version>` in the script URL and a regression test.
