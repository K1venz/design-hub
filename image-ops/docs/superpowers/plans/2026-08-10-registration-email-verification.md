# Registration Email Verification Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Require a six-digit email verification code before account creation and HS256 JWT issuance, complete the headers on every SMTP message, and validate registration and password reset end to end in production.

**Architecture:** Registration requests are repository-owned atomic claims with an unguessable public challenge ID, a separate delivery CAS ID, and explicit `pending_delivery -> active -> consumed` state. Only the claim winner sends mail; only an SMTP-successful expected-delivery CAS becomes verifiable. New registration and resend rotate the public identity returned to the initiating browser. `AccountService` coordinates validation and delivery while the repository owns issuance/resend cooldown, completion, and exact cross-database conflict handling. FastAPI exposes the breaking identity-bound contract; React retains only email plus challenge ID in memory. The shared SMTP adapter owns all standard message headers.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, SQLAlchemy async, Alembic, PostgreSQL, pytest, React 19, TypeScript, TanStack Query, Vitest, Nginx, Docker Compose, Postfix/OpenDKIM.

## Global Constraints

- Use `uv run` for every Python command; do not use system Python or `pip`.
- Follow red-green-refactor for every behavior change and commit each completed task immediately.
- Do not retain `PASSWORD_RESET_CODE_PEPPER` as an alias; deployment and application switch atomically to `EMAIL_VERIFICATION_CODE_PEPPER`.
- Keep login JWT signing on the existing HS256 implementation and existing expiry/renewal behavior.
- Never store or log plaintext verification codes, passwords, RSA ciphertext, or production acceptance recipients.
- Automated tests use generated `example.com` addresses only. Real recipients and test passwords are runtime inputs and must not be written to repository files or shell history.
- Preserve the unrelated untracked `scripts/server-probe.ps1` file.
- Do not push or otherwise interact with a remote Git repository.

---

## Final hardening amendment (authoritative)

- `register` and `resend` return `{message, challenge_id}`; verify and resend
  require that opaque identity. No email-only or old-JWT compatibility path exists.
- Initial issuance and resend use typed atomic repository claims. Pending delivery
  is not verifiable, and expected public/delivery identity CAS is the only
  activation path.
- The browser replaces the rotated resend identifier, uses a deadline-based
  countdown, and never persists password, code, email, or challenge state.
- Production artifacts are staged under `.incoming/<release>` and atomically
  finalized under `releases/<release>`. Maintenance protects migration and API/
  web switching; API images carry the immutable release tag.
- The real environment is snapshotted before an explicit atomic legacy-key
  migration. Normal rollback restores API/worker, SPA, and environment only;
  database restore requires the explicit schema-rollback option.
- General QA logs in with runtime-provided pre-verified accounts. Only the
  separate interactive registration acceptance flow may send registration mail.

---

## Task 1: Add purpose-separated verification-code digests

**Files:**

- Create: `image-code/src/design_hub/application/auth/verification_codes.py`
- Create: `image-code/tests/test_verification_codes.py`
- Modify: `image-code/src/design_hub/application/auth/account_service.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/tests/test_auth.py`
- Modify: `image-code/tests/test_mail_composition.py`

- [ ] Write tests proving `digest_verification_code(purpose, email, code, pepper)` normalizes email, produces a deterministic HMAC-SHA256 hex digest, differs between `registration` and `password-reset`, and rejects a blank pepper or unsupported purpose.
- [ ] Change settings tests to require `EMAIL_VERIFICATION_CODE_PEPPER` in SMTP mode and prove the removed `PASSWORD_RESET_CODE_PEPPER` name does not configure the service.
- [ ] Run `uv run pytest tests/test_verification_codes.py tests/test_mail_composition.py tests/test_auth.py -q` from `image-code` and confirm the new tests fail for the intended missing API.
- [ ] Implement a small shared helper using `hmac.new(..., hashlib.sha256)`, a closed purpose type, normalized email, and `hmac.compare_digest` at call sites.
- [ ] Rename `Settings.password_reset_code_pepper` and the `AccountService` constructor field to the shared email-verification pepper; update password-reset composition with no compatibility alias.
- [ ] Refactor password reset to use purpose `password-reset`, preserving its public behavior, TTL, cooldown, and attempt limit.
- [ ] Re-run the focused tests and `uv run ruff check src tests/test_verification_codes.py tests/test_mail_composition.py tests/test_auth.py`.
- [ ] Commit with `refactor: share purpose-separated verification code digests` and a detailed body describing the security boundary and configuration rename.

## Task 2: Complete the shared transactional mail headers

**Files:**

- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/infrastructure/mail/smtp_mailer.py`
- Modify: `image-code/src/design_hub/infrastructure/mail/composition.py`
- Modify: `image-code/tests/test_mail_composition.py`
- Modify: `image-ops/deploy/.env.example`
- Modify: `image-ops/deploy/scripts/mail-env.sh`
- Modify: `image-ops/deploy/scripts/test-mail-env.sh`
- Modify: `image-ops/deploy/scripts/check-mail-config.sh`
- Modify: `image-ops/deploy/README.md`

- [ ] Add tests that capture the actual `EmailMessage` passed to the SMTP boundary and parse `From`, `Date`, `Message-ID`, and `Auto-Submitted`.
- [ ] Assert the display name/address are configured, `Date` is timezone-aware, two messages have different IDs, the Message-ID domain matches the sender domain, and `Auto-Submitted` equals `auto-generated`.
- [ ] Add composition tests proving SMTP mode rejects a blank `SMTP_FROM_NAME` and malformed sender address before any network access.
- [ ] Add shell-test assertions for exactly one `SMTP_FROM_NAME=Design Hub` entry and the renamed pepper key, including idempotent reruns and conflicting-value failure.
- [ ] Run the focused Python and shell tests and confirm the header/deployment assertions fail.
- [ ] Add `smtp_from_name` to settings; validate it and the sender mailbox fail-fast in SMTP mode; pass both explicitly into `SmtpMailer`.
- [ ] Build the formatted From address with standard-library address utilities, use an aware UTC date, generate a unique sender-domain Message-ID, and add `Auto-Submitted` for every message.
- [ ] Update deployment examples, validation, and provisioning to use `SMTP_FROM_NAME=Design Hub` and `EMAIL_VERIFICATION_CODE_PEPPER`.
- [ ] Run `uv run pytest tests/test_mail_composition.py -q`, `bash image-ops/deploy/scripts/test-mail-env.sh` from a Bash-capable environment, and Ruff on the changed Python files.
- [ ] Commit with `feat: complete transactional email identity headers` and a detailed body describing the shared mail boundary and deployment validation.

## Task 3: Introduce the pending-registration persistence boundary

**Files:**

- Create: `image-code/src/design_hub/ports/registration.py`
- Create: `image-code/src/design_hub/infrastructure/db/registration_repo.py`
- Create: `image-code/migrations/versions/b9c0d1e2f3a4_registration_challenge.py`
- Create: `image-code/tests/test_registration_repository.py`
- Modify: `image-code/src/design_hub/infrastructure/db/models.py`

- [ ] Define immutable port values for pending/active delivery, typed initial/resend claim outcomes, expected-identity activation/invalidation, failed-attempt CAS, and atomic completion.
- [ ] Specify `complete(...)` to lock the active row, recheck expiry/attempts/digest preconditions supplied by the service, create one `AppUser` with `Role.DESIGNER`, set `consumed_at`, and return either the created account or a typed duplicate/invalid outcome without committing partial state.
- [ ] Add repository tests for identity rotation, provisional activation, atomic claim cooldown/contended outcomes, invalidation, failed-attempt increments, row consumption, atomic user creation, and concurrent issuance/resend/completion winners.
- [ ] Run `uv run pytest tests/test_registration_repository.py -q` and confirm it fails because the port, model, migration, and repository do not exist.
- [ ] Add `RegistrationChallengeRow` with unguessable public/delivery IDs, unique normalized email, pending/active/consumed state, identity data, code digest, expiry/attempt count, microsecond claim/activation timestamps, and consumed timestamp.
- [ ] Add Alembic revision `b9c0d1e2f3a4` with `down_revision = "a8b9c0d1e2f3"`, table constraints/indexes, and a complete downgrade.
- [ ] Implement `SqlAlchemyRegistrationStore`; atomically claim issuance/resend under row lock or unique insert, classify only exact MySQL/PostgreSQL/SQLite conflicts, activate expected delivery by CAS, and translate only the user-email completion race into a typed duplicate.
- [ ] Run the repository tests, `uv run alembic heads` (expect one head), `uv run alembic upgrade head` against the test database path used by the suite, and Ruff.
- [ ] Commit with `feat: add pending registration persistence` and a detailed body describing the transaction and concurrency guarantees.

## Task 4: Implement registration request, verification, and resend use cases

**Files:**

- Modify: `image-code/src/design_hub/application/auth/account_service.py`
- Modify: `image-code/src/design_hub/ports/registration.py`
- Modify: `image-code/tests/test_auth.py`

- [ ] Extend the in-memory test doubles and write service tests for request-without-user/JWT, successful verify, pending-user login failure, duplicate registered email, malformed code, expired code, exhausted attempts, wrong code, superseded code, resend cooldown, resend replacement, initial-send failure, resend failure, and one-winner concurrent verification.
- [ ] Assert all invalid/expired verification paths expose one generic message and no path returns a token before the repository reports successful atomic completion.
- [ ] Run `uv run pytest tests/test_auth.py -q` and confirm the new cases fail.
- [ ] Replace immediate `register` with `request_registration`; obtain a typed atomic claim, send only as the winner, then activate only the expected pending delivery and return its public ID.
- [ ] On initial or resend delivery/activation failure invalidate the exact delivery. Resend claims and rotates public/delivery IDs while preserving stored profile/password hash; double failures never return a usable identity.
- [ ] Implement `verify_registration` with format/expiry/attempt checks and constant-time digest comparison, then call the repository atomic completion and issue the existing HS256 login JWT only from its successful result.
- [ ] Refactor shared code-generation, timezone, and mail-copy helpers only where they eliminate duplication without changing password-reset behavior.
- [ ] Run the auth tests and Ruff.
- [ ] Commit with `feat: require email verification for registration` and a detailed body explaining pending state, resend invalidation, and post-commit JWT issuance.

## Task 5: Expose and compose the new backend API

**Files:**

- Modify: `image-code/src/design_hub/interface/api/auth_schemas.py`
- Modify: `image-code/src/design_hub/interface/api/routes/auth.py`
- Modify: `image-code/src/design_hub/interface/api/deps.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/tests/test_auth.py`
- Modify: `image-code/tests/test_mail_composition.py`

- [ ] Add HTTP tests proving register/resend return acknowledgement plus opaque `challenge_id`, verify/resend require it, and successful verify alone returns unchanged `LoginResponse`.
- [ ] Cover validation and status mapping: registered email 409, malformed input 400/422 according to the existing route convention, generic verification failure 400, and login for pending email 401.
- [ ] Run focused tests and confirm they fail on the old single-step contract.
- [ ] Add request/response schemas with required opaque `challenge_id`, a six-digit code constraint, and no password/name fields on resend or verify.
- [ ] Replace the register route response model, add verify/resend routes, and keep exception translation consistent with existing auth routes.
- [ ] Add registration TTL/cooldown/max-attempt settings with 600/60/5 defaults and bounds; compose `SqlAlchemyRegistrationStore` and pass the shared pepper and limits into `AccountService`.
- [ ] Verify startup fails in SMTP mode when shared mail security configuration is missing.
- [ ] Run `uv run pytest tests/test_auth.py tests/test_mail_composition.py tests/test_docs_gate.py -q` and Ruff.
- [ ] Commit with `feat: expose verified registration API` and a detailed body describing the intentional breaking contract.

## Task 6: Regenerate the API contract and update frontend mutations

**Files:**

- Modify (generated): `image-code/openapi.json`
- Modify (generated): `image-web/openapi.json`
- Modify (generated): `image-web/src/api/schema.d.ts`
- Modify: `image-web/src/api/auth.ts`
- Create: `image-web/src/api/auth.test.ts`

- [ ] Add frontend API tests proving acknowledgement leaves complete auth/storage state unchanged, verify sends email/challenge/code and stores only the successful session, resend sends email/challenge and adopts the rotated acknowledgement ID, and encryption rejection makes zero fetch calls.
- [ ] Run `npm test -- src/api/auth.test.ts` from `image-web` and confirm failures against the old mutation design.
- [ ] Export OpenAPI from `create_production_app().openapi()` into `image-code/openapi.json`, copy the identical document to `image-web/openapi.json`, and run `npm run gen:api`; never hand-edit generated files.
- [ ] Refactor `useRegister` to request a code, add `useVerifyRegistration` to persist the successful LoginResponse, and add `useResendRegistration` without accepting password/name.
- [ ] Run the API test, `npm run typecheck`, and verify `image-code/openapi.json` and `image-web/openapi.json` are byte-identical.
- [ ] Commit with `feat: update client registration contract` and a detailed body describing session creation only after verification.

## Task 7: Build the two-step registration interface

**Files:**

- Modify: `image-web/src/pages/RegisterPage.tsx`
- Create: `image-web/src/pages/RegisterPage.test.tsx`
- Modify only if reuse is clean: `image-web/src/pages/ForgotPasswordPage.tsx`

- [ ] Write jsdom interaction tests for form submission, transition to the verification step, masked pending email copy, six-digit input, successful authenticated navigation, resend disabled/countdown/enabled behavior, generic invalid-code display, expired-state recovery, and return-to-form behavior.
- [ ] Assert neither plaintext password nor verification code is written to localStorage/sessionStorage and profile/password inputs are not resent by the resend action.
- [ ] Run `npm test -- src/pages/RegisterPage.test.tsx` and confirm the new workflow tests fail.
- [ ] Implement an in-memory page state machine for `details -> verification`; discard plaintext password immediately and retain one `{email, challengeId}` value only in component memory.
- [ ] Add accessible step state, code entry, deadline-based resend countdown that restarts after zero, correct error precedence, masked email presentation, and explicit edit/restart action.
- [ ] On verification success rely on the mutation's auth-store update and navigate through the existing post-login behavior.
- [ ] Run the page test, full `npm test`, `npm run typecheck`, `npm run lint`, and `npm run build`.
- [ ] Commit with `feat: add two-step registration experience` and a detailed body describing transient state and recovery behavior.

## Task 8: Add production Nginx limits and deployment verification

**Files:**

- Modify: `image-ops/deploy/nginx/conf.d/design-hub.conf`
- Create: `image-ops/deploy/scripts/test-registration-ratelimits.sh`
- Modify: `image-ops/deploy/README.md`
- Modify: `image-ops/deploy/scripts/check-mail-config.sh`

- [ ] Add a structural Nginx test requiring the generic HTTPS `/api/` and every exact auth location to reuse the shared proxy include, with commented/missing/duplicate/wrong-server negative fixtures.
- [ ] Extend config checks to reject the removed pepper name, require the shared pepper and branded sender name, and never print secret values.
- [ ] Run the shell checks and confirm they fail before the Nginx routes/config checks are implemented.
- [ ] Split IP rate-limit zones so initial registration and resend are strict while verification permits normal code-entry retries; add exact locations for `/api/auth/register/verify` and `/api/auth/register/resend` without weakening current login/generation controls.
- [ ] Implement and document immutable release staging, environment snapshot/atomic rename, maintenance protection, candidate migration/health, controlled API/web switch, automatic rollback, and explicit-only schema restore.
- [ ] Run `nginx -t` in the deployment container/config harness, the new rate-limit test, and all mail environment checks.
- [ ] Commit with `ops: protect verified registration endpoints` and a detailed body describing endpoint-specific abuse controls and deployment requirements.

## Task 9: Full local verification and production acceptance

**Files:**

- No production recipient or password files are created or modified.
- Update only if verification exposes an actual defect: the smallest owning source/test file, followed by a separate fix commit.

- [ ] From `image-code`, run `uv run pytest -q`, `uv run ruff check src tests`, `uv run alembic heads`, and a clean migration upgrade against the configured verification database.
- [ ] From `image-web`, run `npm test`, `npm run lint`, `npm run typecheck`, and `npm run build`.
- [ ] Run deployment shell checks, `docker compose config`, and Nginx configuration validation without displaying secrets.
- [ ] Inspect `git status --short` and `git diff --check`; confirm only intentional committed changes plus the preserved unrelated untracked probe file remain.
- [ ] Stage a versioned release, let the orchestrator snapshot/migrate the environment under maintenance, back up/migrate with the immutable candidate image, switch API/worker and SPA together, and confirm API, Nginx, Postfix, and OpenDKIM health plus an empty mail queue.
- [ ] Accept the registration recipient interactively in process memory, execute the public registration request, obtain the received code from the user, verify it, confirm the JWT header declares HS256, log in, and prove code reuse fails.
- [ ] Accept the existing reset recipient interactively, confirm the account exists before mutating it, obtain explicit approval for the new password, complete forgot/reset/login, and prove reset-code reuse fails.
- [ ] Inspect the received Gmail messages for branded From, Date, unique sender-domain Message-ID, Auto-Submitted, SPF pass, DKIM pass, DMARC pass, and record inbox placement separately from transport success without committing recipient data.
- [ ] Confirm the Postfix queue is empty and services remain healthy. Do not delete the test account unless the user separately authorizes cleanup.

## Completion Criteria

- Unverified registrations never create `app_user` rows and cannot log in.
- Old or missing challenge identities cannot verify or resend, and concurrent
  issuance/resend has exactly one mail-sending winner.
- No code is verifiable before successful expected-delivery activation.
- Successful verification atomically creates exactly one user and only then returns the existing HS256 login JWT.
- Registration and password-reset digests use the shared secret with distinct HMAC-SHA256 purposes.
- Every SMTP message contains the approved branded standard headers.
- Frontend, backend, migration, deployment, and abuse-control tests pass.
- Both user-supplied runtime acceptance flows pass without any real test data entering committed artifacts.
