# Registration Email Verification Design

## Objective

Require proof of email ownership before creating an application account. A
registration request remains pending until its six-digit code is verified; only
then does the system create the user and issue the existing HS256 login JWT.

## User Flow

1. The user enters email, name, and password on the registration page.
2. The browser encrypts the password with the existing RSA-OAEP public key.
3. `POST /auth/register` validates the request, creates a pending registration,
   and emails a six-digit verification code. It does not create an `app_user`
   row or issue a JWT.
4. The registration page moves to a verification step with a resend countdown.
5. `POST /auth/register/verify` validates the email and code. Success atomically
   creates the user, consumes the pending registration, and returns the normal
   login response with an HS256 JWT.
6. `POST /auth/register/resend` replaces the code while retaining the pending
   email, password hash, and name.

An already registered email is rejected with HTTP 409. An unverified email is
not a user and cannot log in.

## Pending Registration Model

The new `registration_challenge` table stores one row per normalized email:

- normalized email as a unique key;
- display name;
- password hash, never the plaintext or RSA ciphertext;
- HMAC-SHA256 verification-code digest;
- expiry timestamp;
- failed-attempt count;
- creation and last-send timestamps;
- consumed timestamp.

Both registration and password reset use a renamed server-only
`EMAIL_VERIFICATION_CODE_PEPPER`, with distinct purpose prefixes in their HMAC
input. Their digests therefore cannot be substituted for each other. The old
`PASSWORD_RESET_CODE_PEPPER` setting is replaced in the same release rather than
retained as a compatibility alias. The shared helper uses HMAC-SHA256 rather than
concatenated plain SHA-256 input.

The code is valid for ten minutes, resend is blocked for sixty seconds, and five
failed attempts lock the current challenge. Resend invalidates the prior code.
Plaintext codes are never stored or logged.

## Transaction Boundary

Verification locks the pending registration row and rechecks that no user owns
the email. User creation and challenge consumption occur in one database
transaction. Unique constraints remain the final concurrency guard. A duplicate
created concurrently is returned as HTTP 409 without issuing a JWT.

The registration repository owns this transaction rather than coordinating two
independent repositories from the application service.

## Email Delivery

Registration and password-reset email both use the shared branded
`SmtpMailer`. Every message carries:

- `From: Design Hub <no-reply@image.sepaitech.com>`;
- an RFC-compliant UTC `Date`;
- a unique sender-domain `Message-ID`;
- `Auto-Submitted: auto-generated`.

If initial registration email delivery fails, the pending challenge is
invalidated and the request fails. If resend delivery fails, the newly generated
code is invalidated; the superseded code does not become valid again.

## JWT

Email verification codes are not JWTs. The system continues to use only the
existing HS256 login JWT after successful verification. The production JWT
secret remains the high-entropy server environment secret, and the existing
24-hour expiry and renewal behavior remain unchanged.

## API and Frontend Contract

`POST /auth/register` changes from `LoginResponse` to an acknowledgement response.
There is no backward-compatibility endpoint. The frontend is updated in the same
release.

`POST /auth/register/verify` accepts normalized email and a six-digit code and
returns `LoginResponse`.

`POST /auth/register/resend` accepts the email and returns an acknowledgement.
It does not accept replacement profile or password data.

The UI preserves the pending email between steps, masks it in explanatory copy,
supports resend after the cooldown, and returns to the registration form when
the pending request has expired. Passwords and codes are not persisted in local
storage.

## Rate Limits and Enumeration

Application rules enforce per-email cooldown and attempt limits. nginx applies
IP limits to register, verify, and resend endpoints. Registered-email conflicts
retain the current explicit 409 behavior; verification failures use one generic
invalid-or-expired-code message.

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
- resend cooldown and replacement behavior;
- mail failure invalidates the new challenge;
- duplicate and concurrent verification cannot create duplicate users;
- pending users cannot log in;
- code digests are purpose-separated HMAC-SHA256 values;
- branded standard mail headers are present and Message-IDs are unique.

Frontend tests cover the registration step transition, code submission, resend
countdown, expiry recovery, and successful authenticated navigation.

Deployment checks cover the new environment value and nginx rate-limit routes.
The complete backend and frontend suites, Ruff, TypeScript compilation, and
production build must pass before deployment.

## Production Acceptance

1. Deploy the application and migration after taking the normal database backup.
2. Verify all containers are healthy and the Postfix queue is empty.
3. Register `zhaok157+designhub-test@gmail.com`, receive the code in the
   `zhaok157@gmail.com` Gmail inbox, verify it, and confirm login succeeds.
4. Confirm the registration code cannot be reused.
5. Request a reset for the existing `zhaok157@gmail.com` account, receive the
   code, submit a user-approved new password, and confirm login succeeds.
6. Confirm the reset code cannot be reused and the mail queue remains empty.
7. Inspect Gmail authentication results for SPF, DKIM, and DMARC pass status and
   record inbox placement separately.

The test account is not deleted automatically. Any cleanup is a separate,
explicitly authorized operation.

## Rollback

Rollback restores the pre-release application image and database backup when
schema rollback is required. DNS and SMTP services are unchanged. Because the
frontend and registration API contract change together, they roll back together.
