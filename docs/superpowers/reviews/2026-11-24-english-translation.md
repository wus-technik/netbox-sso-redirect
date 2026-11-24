# Review: English translation (2026-11-24)

## Verdict

**Approved: no functional regression found in the translation changes.**

Scope: README, historical implementation plan and reviews, package/plugin descriptions,
Python docstrings and comments, JavaScript/template comments, plugin-owned UI messages,
validation errors, and log messages. NetBox-owned translations remain controlled by NetBox.
Historical findings, commit references, and outcomes were retained; the plan is explicitly
marked historical. The README now explains where dependency and plugin versions originate.

## Verification

- Compared production Python ASTs with `HEAD` (`d920301`), excluding docstrings.
  All remaining differences were individually inspected string constants: descriptions,
  validation messages, the blocked-login response, and log messages. Control flow,
  imports, identifiers, configuration keys, defaults, URLs, and version bounds are unchanged.
- Compared JavaScript after removing comment-only lines: identical.
- Compared HTML tags/attributes and Django template tags/expressions after removing
  template comments: identical. Only visible text changed; CSRF, escaping, form fields,
  IDs, selectors, `data-autostart`, conditional links, and versioned script loading remain intact.
- Parsed `pyproject.toml`: only the project description differs.
- Updated the existing local-login test assertion to the English label. Security tests
  added in the preceding review remain in place; no test was removed or weakened.
- Reviewed the documentation changes, checked balanced Markdown fences and local links,
  and searched for remaining German prose. The `/anmelden/` test fixture remains unchanged
  because it is an arbitrary URL used to test runtime `LOGIN_URL` overrides.
- Python compilation, JavaScript syntax, Compose validation, and `git diff --check` passed.

Regression runs against the pinned NetBox 4.7.3 image:

| Run | Result |
|---|---|
| `manage.py test netbox_sso_redirect --keepdb -v 1` | 89 discovered, 85 passed, four prefix-only tests skipped as expected; exit 0 |
| `BASE_PATH=netbox/`, `manage.py test netbox_sso_redirect.tests.test_base_path --keepdb -v 1` | All four passed; exit 0 |

The normal test run covers template rendering and escaping, headers, CSRF, password
blocking, API tokens, SSO start, error recovery, and PKCE start parameters. No new browser
layout check or live authentik end-to-end test was performed. Existing test-environment
warnings about API v2 token peppers and `LOGIN_REQUIRED` deprecation are unchanged.

## Remaining release conditions

This translation changes neither dependency versions nor the status of the
[security review](2026-11-24-security-1.0.0.md). Production OIDC/PKCE and Django patch-level
checks remain open. The localhost-only development port bindings and eight security tests
are changes from that preceding review, not effects of translation.

The intended observable changes are English plugin-owned UI, error, and log text.
External log consumers matching German message text would need corresponding updates;
logger names, levels, placeholders, HTTP statuses, and JSON keys are unchanged.
