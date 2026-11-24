# Review: specification in README.md (2026-11-18)

**Scope:** README as the specification, including decisions on POST, `next`, testing,
and integration; also `pyproject.toml` and the initial `netbox_sso_redirect/__init__.py`
scaffold. Ref: ITSYS-422.

**Model/command:** Codex CLI 0.170.0, `gpt-6.1-terra`, medium reasoning,
`codex exec --sandbox read-only --cd <repo> --model gpt-6.1-terra ...`.
Codex read NetBox v4.7.3 sources (`settings.py`, `account/views.py`, `urls.py`,
`middleware.py`, `login.html`); NetBox claims were independently checked against
the same files. social-core/social-app-django sources and authentik behavior were not checked.

**Result:** CHANGES_REQUESTED. No fundamental design error, but gaps in the specification.
All findings were incorporated into the README.

| # | Severity | Location | Finding | Verdict | Resolution |
|---|---|---|---|---|---|
| 1 | high | README, behavior 1 | Native form POST fails under CSP `form-action 'self'` because Chromium checks every redirect hop, as documented by NetBox's `SocialAuthBeginView`. Inline scripts may violate `script-src`. | confirmed | Use `fetch` with JSON Accept and `location.assign`, a static script, and a form/button fallback; record proxy CSP before rollout |
| 2 | high | README, behavior 1/2 | `next` must be a POST field to the begin view; validation and fallback were imprecise (`/` versus `LOGIN_REDIRECT_URL`). | confirmed for NetBox, likely for social-core | Escaped hidden field; `url_has_allowed_host_and_scheme` with `require_https`; configured fallback and explicit tests |
| 3 | high | README, behavior 1 | The CSRF cookie is `HttpOnly`, requiring a rendered token; cache/framing headers unspecified. | confirmed | Render `get_token()` in form; `no-store, private`, `X-Frame-Options: DENY`; full-stack header test |
| 4 | moderate (Codex: high) | README, image | `?local=1` only shows the form with `LOGIN_FORM_HIDDEN = False`. | confirmed | Document prerequisite in plugin and image sections |
| 5 | moderate | README, rationale / behavior 1 | Conflates NetBox's `social_auth_begin` and social-django's `social:begin`; fixed path ignores `BASE_PATH`. | confirmed | Use `reverse('social_auth_begin', args=[backend])`; separate explanations |
| 6 | moderate | README, behavior 1 | HEAD should neither start SSO nor create a token. | partial | Intercept only GET; pass HEAD to NetBox, replacing the prior GET-or-HEAD decision. Plan-review correction: NetBox's own login page also sets a CSRF cookie on HEAD; the plugin only avoids creating one itself |
| 7 | moderate | README, image | Login loop risk: override must include `BASE_PATH`; plugin settings unvalidated. | confirmed | Document prefix; validate at startup, disable redirect and warn on errors |
| 8 | moderate | README, image | Logout lacks `id_token_hint`; landing page must not be `/login/`. | NetBox confirmed, authentik unresolved | Document landing-page rule; verify authentik end-to-end |
| 9 | low (Codex: moderate) | README, behavior 1 | `LOGIN_URL` comparison, authenticated users, `local` variants, and other query parameters unspecified. | confirmed | Explain and test each |
| 10 | moderate | README, development | Tags are movable; tokens can leak into layers/logs. | confirmed | Pin commit SHA; use BuildKit secrets only |
| 11 | moderate | README, development | Test setup too vague. | confirmed | Image digest, PostgreSQL/Redis, `manage.py test`, test matrix |
| 12 | low (Codex: moderate) | README, behavior 2 | `get_host()` and `is_secure()` depend on proxy configuration (`USE_X_FORWARDED_HOST`). | confirmed | Document proxy prerequisites in image section |
| 13 | low | `netbox_sso_redirect/__init__.py:14` | `max_version = "4.7.99"` excludes 4.8. | intentional | Document review during NetBox upgrades |
| 14 | low | `pyproject.toml:15` | Dynamic version via `attr` can fail for a computed value. | no current bug | Retain literal and document it |

**Confirmed without changes:** `PluginConfig.middleware` is appended to `MIDDLEWARE`;
`request.user` is available; `LoginView.post()` does not check `LOGIN_FORM_HIDDEN`;
allowing POST to `/login/` is an accepted design decision, requiring a strong
password for `admin`.
