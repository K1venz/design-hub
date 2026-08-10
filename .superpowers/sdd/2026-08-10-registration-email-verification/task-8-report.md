# Task 8 report: Nginx registration protection and deployment verification

## Changes

- Added exact-match Nginx locations for registration verification and resend.
- Kept `/api/auth/register` at `reg` 5r/m with burst 3; resend uses the stricter independent `reg_resend` zone at 3r/m with burst 2; verification uses `reg_verify` at 12r/m with burst 6 so normal code-entry retries remain usable.
- All three registration endpoints include the existing shared API proxy block. The static semantic test also protects the unchanged login rate limit and proxy include.
- Added `test-registration-ratelimits.sh`, which parses location blocks and checks their zones, rates, bursts, and shared proxy directives rather than checking documentation text.
- `check-mail-config.sh` now validates the example environment before Compose resolution, rejects `PASSWORD_RESET_CODE_PEPPER`, requires `EMAIL_VERIFICATION_CODE_PEPPER` and `SMTP_FROM_NAME=Design Hub`, and reports only key names rather than values. `PYTHON_BIN` permits the Windows validation harness to use uv-managed Python while production continues to default to `python3`.
- Documented database backup, pepper rename, migration, coordinated backend/frontend rollout, health checks, Nginx validation, and image-plus-database rollback.

## TDD evidence

- RED: the new rate-limit test initially failed with `missing exact location for /api/auth/register/resend`.
- GREEN: after the Nginx changes, `test-registration-ratelimits.sh` exits 0 with `registration rate limits: OK`.
- Legacy-pepper negative test: adding a temporary `PASSWORD_RESET_CODE_PEPPER=legacy-placeholder` fixture caused `check-mail-config.sh` to exit 1 with `PASSWORD_RESET_CODE_PEPPER is no longer supported`; the value was not printed. The fixture was removed before commit.

## Verification

Passed:

```text
scripts/test-registration-ratelimits.sh
registration rate limits: OK

scripts/test-mail-env.sh
mail environment provisioning: OK

git diff --check
exit 0
```

Not run successfully in this Windows worktree:

```text
scripts/check-mail-config.sh
scripts/check-mail-config.sh: line 42: docker: command not found
```

The example-environment validation ran before this expected Docker failure. Docker and a local `nginx` executable are unavailable, so `docker compose config` and container `nginx -t`/`nginx -T` were not verified. No success result was substituted for them.

## Self-review

- Exact-match routes prevent the broader `/api/` location from bypassing endpoint limits.
- The shared proxy include preserves the existing rewrite, upstream, and forwarding headers.
- Existing login controls are explicitly guarded by the test; generation controls were not modified.
- No secrets were added or printed.
