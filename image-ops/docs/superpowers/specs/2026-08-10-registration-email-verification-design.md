# Registration Email Verification Design

## Objective

Require proof of email ownership before creating an application account. A
registration request remains pending until its six-digit code is verified; only
then does the system create the user and issue the existing HS256 login JWT.

## User Flow

1. The user enters email, name, and password on the registration page.
2. The browser encrypts the password with the existing RSA-OAEP public key.
3. `POST /auth/register` atomically claims a provisional registration, emails a
   six-digit verification code, activates only that delivered claim, and returns
   an unguessable `challenge_id`. It does not create an `app_user` row or issue
   a JWT.
4. The registration page moves to a verification step with a resend countdown.
5. `POST /auth/register/verify` validates the email, `challenge_id`, and code.
   Success atomically creates the user, consumes the active registration, and
   returns the normal login response with an HS256 JWT.
6. `POST /auth/register/resend` atomically claims a replacement delivery while
   retaining the email, password hash, and name. It rotates and returns the
   public `challenge_id`; the browser replaces its in-memory identifier.

An already registered email is rejected with HTTP 409. An unverified email is
not a user and cannot log in.

## Pending Registration Model

The new `registration_challenge` table stores one row per normalized email:

- an unguessable public challenge identifier, rotated by a new registration or
  resend and returned only after activation succeeds;
- a separate unguessable delivery identifier used only for repository CAS;
- normalized email as a unique key;
- display name;
- password hash, never the plaintext or RSA ciphertext;
- HMAC-SHA256 verification-code digest;
- expiry timestamp;
- failed-attempt count;
- explicit `pending_delivery`, `active`, and `consumed` delivery state;
- creation, delivery-claim, and activation timestamps;
- consumed timestamp.

Both registration and password reset use a renamed server-only
`EMAIL_VERIFICATION_CODE_PEPPER`, with distinct purpose prefixes in their HMAC
input. Their digests therefore cannot be substituted for each other. The old
`PASSWORD_RESET_CODE_PEPPER` setting is replaced in the same release rather than
retained as a compatibility alias. The shared helper uses HMAC-SHA256 rather than
concatenated plain SHA-256 input.

The code is valid for ten minutes, resend is blocked for sixty seconds, and five
failed attempts lock the current challenge. A new registration request rotates
the browser identity, so an older browser cannot verify replacement profile or
password data. Resend rotates both delivery and public identities, making an
ambiguous activation result unusable because the replacement identifier was not
returned. Plaintext codes are never stored or logged.

## Transaction Boundary

Initial issuance and resend are typed repository claims. Each claim locks or
atomically inserts the email row, rechecks cooldown and the expected public
identity, and returns claimed, cooldown, contention, invalid, or already-
registered. Only the claimed winner sends mail. Exact MySQL, PostgreSQL, and
SQLite uniqueness/deadlock classifications are translated; unrelated database
errors propagate.

Verification uses both public and delivery identities. User creation and
challenge consumption occur in one database transaction. Unique constraints
remain the final concurrency guard. A duplicate created concurrently is returned
as HTTP 409 without issuing a JWT.

The registration repository owns this transaction rather than coordinating two
independent repositories from the application service.

## Email Delivery

Registration and password-reset email both use the shared branded
`SmtpMailer`. Every message carries:

- `From: Design Hub <no-reply@image.sepaitech.com>`;
- an RFC-compliant UTC `Date`;
- a unique sender-domain `Message-ID`;
- `Auto-Submitted: auto-generated`.

Every claimed code starts as `pending_delivery` and is therefore unverifiable.
After SMTP succeeds, an expected-public-ID plus expected-delivery-ID CAS changes
only that claim to `active`. Delivery or activation failure attempts the same
identity-bound invalidation. Even when delivery/activation and invalidation fail
together, no usable challenge identity is returned; an older identifier cannot
address the replacement delivery.

## JWT

Email verification codes are not JWTs. The system continues to use only the
existing HS256 login JWT after successful verification. The production JWT
secret remains the high-entropy server environment secret, and the existing
24-hour expiry and renewal behavior remain unchanged.

## API and Frontend Contract

`POST /auth/register` changes from `LoginResponse` to
`{message, challenge_id}`. There is no backward-compatibility endpoint. The
frontend is updated in the same release.

`POST /auth/register/verify` accepts normalized email, `challenge_id`, and a
six-digit code and returns `LoginResponse`.

`POST /auth/register/resend` accepts email and `challenge_id`, and returns an
acknowledgement containing the rotated `challenge_id`. It does not accept
replacement profile or password data.

The UI preserves only `{email, challengeId}` in component memory between steps,
masks the email in explanatory copy, restarts a deadline-based countdown after
resend, and returns to the form when the pending request has expired. Passwords,
codes, and registration identity are not persisted in browser storage.

## Rate Limits and Enumeration

Repository claims enforce per-email cooldown; active-delivery CAS enforces
attempt limits. nginx applies IP limits to register, verify, and resend endpoints.
Registered-email conflicts retain the current explicit 409 behavior;
verification failures use one generic invalid-or-expired-code message.

## Migration and Existing Accounts

The migration only adds `registration_challenge`. Existing `app_user` rows are
not modified and continue to log in normally. No `email_verified` compatibility
state is added because accounts are created only after verification from this
release onward.

## Automated Verification

Backend tests cover:

- registration request sends a code but creates no user or JWT;
- successful verification creates exactly one user and returns HS256 JWT;
- invalid, expired, exhausted, and superseded codes fail;
- atomic issuance/resend ownership and cooldown under concurrency;
- public identity rotation prevents password/profile takeover;
- pending delivery is unverifiable until exact activation CAS;
- mail, activation, and invalidation double failures remain fail-closed;
- duplicate and concurrent verification cannot create duplicate users;
- pending users cannot log in;
- code digests are purpose-separated HMAC-SHA256 values;
- branded standard mail headers are present and Message-IDs are unique.

Frontend tests cover challenge propagation/rotation, storage and auth-state
invariants, the zero-to-resend-to-zero countdown, error precedence, step
accessibility, expiry recovery, and successful authenticated navigation.

Deployment checks execute version staging, legacy environment snapshot/migration,
maintenance protection, candidate health, web switching, automatic rollback,
and explicit-only schema restore. They also cover the new environment value and
nginx generic/exact proxy semantics. The complete backend and frontend suites,
Ruff, TypeScript compilation, and production build must pass before deployment.

## Production Acceptance

1. Stage one immutable release and let the release orchestrator snapshot the
   environment, enable maintenance, back up the database, and migrate with the
   candidate image.
2. Verify all containers are healthy and the Postfix queue is empty.
3. Register a user-supplied runtime test alias, receive the code in its inbox,
   verify it, and confirm login succeeds.
4. Confirm the registration code cannot be reused.
5. Request a reset for a user-supplied existing test account, receive the code,
   submit a user-approved new password, and confirm login succeeds.
6. Confirm the reset code cannot be reused and the mail queue remains empty.
7. Inspect Gmail authentication results for SPF, DKIM, and DMARC pass status and
   record inbox placement separately.

The test account is not deleted automatically. Any cleanup is a separate,
explicitly authorized operation.

## Test Data Boundary

Acceptance email addresses and passwords are supplied interactively at runtime.
They must not be embedded in production code, frontend bundles, application
defaults, deployment files, migrations, committed fixtures, reusable test
constants, or log messages. Automated tests use generated `example.com`
addresses that cannot reach a real inbox. Production acceptance commands keep
recipient values in process memory only and do not write them to repository
files.

## Rollback

Normal rollback restores the previous immutable API/worker image, versioned SPA,
and pre-release environment snapshot together. It does not restore the database.
Database restore is available only through the explicit schema-rollback option
and an operator-supplied backup. DNS and SMTP services are unchanged.
