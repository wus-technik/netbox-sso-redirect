# Review: preserving `next` after SSO errors, preconnect, spinner (0.3.0, 2026-11-19)

**Scope:** Version 0.3.0, branch `feature/ITSYS-422-sso-error-next`, commits
`cc77589..754a088`, plus fixes from this review. Prompted by feedback from the
docker-netbox-wus staging test. Ref: ITSYS-422.

**Model/command:** Codex CLI 0.170.0 via the `codex-reviewer` agent,
`codex exec --sandbox read-only --cd <repo> --model gpt-6.1-sol -c model_reasoning_effort=high - < <prompt>`
(prompt via stdin). Codex read pinned social-core 5.2.0, social-app-django 6.1.0,
and NetBox 4.7.3 sources but had no Docker access. Tests ran in the NetBox 4.7.3
container: `$TEST` 81 OK, four skipped; `$TEST_BP` four OK.

**Result:** APPROVE. Codex reported no critical, high, or moderate findings.

| # | Severity | Location | Finding | Verdict | Resolution |
|---|---|---|---|---|---|
| 1 | low | `conf.py` `get_idp_origin` | A malformed endpoint such as `https://[idp.example/x` causes `urlsplit` to raise `ValueError`, returning 500 from the bridge. | valid | Catch `ValueError`, including invalid ports, and omit preconnect; tests added |
| 2 | low | `conf.py` `get_idp_origin` | Building the origin from `netloc` could expose endpoint credentials (`user:pw@`) in HTML. Agent observation. | valid | Build from `hostname` and `port`, bracket IPv6; tests added |
| 3 | low | `tests/test_base_path.py` | Restoring `next` was not tested under `BASE_PATH`. | valid | Added `test_restore_next_with_prefix` |
| 4 | low | `tests/test_sso_error.py` | The docstring described a valid state, but social-core evaluates `error` before state. | valid | Clarified the docstring; the test still exercises the real error path |

**Confirmed by Codex:**

- `do_auth` sets `session["next"]`; `SocialAuthExceptionMiddleware` leaves the session unchanged.
- No open redirect or loop; the 302 response is `no-store`, and parameters are retained.
- No `crossorigin` is needed; template escaping is sufficient.
- Returning from the back-forward cache does not automatically restart login.
- The README matches the implementation.

**Residual risk documented in the README:** an older `next` value can remain in the
session if a later start omits it. It is still validated; at worst the user lands
on another page on the same host.

## Manual check (browser, local stack)

Callback `/oauth/complete/oidc/?error=access_denied&state=<current>` after starting
from `/dcim/devices/`:

- **Local login blocked:** destination `/login/?local=1&next=%2Fdcim%2Fdevices%2F`;
  bridge without auto-start, `next` present in the form, exactly one "Single sign-on failed …" toast.
- **Local login allowed:** same destination, NetBox form containing `next`, one visible toast.
  The second text in the staging report ("Unable to begin single sign-on …") is
  NetBox's hidden `#sso-error` block (`d-none`) in `login.html`, not a second message.
