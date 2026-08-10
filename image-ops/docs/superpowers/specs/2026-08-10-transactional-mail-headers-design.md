# Transactional Mail Headers Design

## Objective

Make every transactional email sent by `SmtpMailer` carry a complete,
consistent identity, then validate the production password-reset flow through
Gmail from request to successful login with the new password.

## Scope

This change covers the shared SMTP message envelope and the production
password-reset acceptance flow. It does not add marketing-email features,
inbound email, unsubscribe support, or an HTML template system.

## Message Identity

`SmtpMailer` owns the headers that must be present on every transactional
message. Callers continue to supply only the recipient, subject, and text body.
The mailer adds:

- `From: Design Hub <no-reply@image.sepaitech.com>`
- `Date` formatted as an RFC-compliant UTC timestamp
- a unique `Message-ID` whose right-hand domain matches the sender domain
- `Auto-Submitted: auto-generated`

`SMTP_FROM_NAME` configures the display name and is fixed to `Design Hub` in
the production deployment. The sender address remains configured by
`SMTP_FROM`. Both values must be non-empty in SMTP delivery mode.

No `Reply-To` header is added because there is no monitored inbound mailbox.
No `List-Unsubscribe` header is added because password reset is transactional,
not subscription or marketing mail.

## Configuration and Deployment

The application settings, composition root, production `.env` example, and
idempotent environment provisioning all adopt `SMTP_FROM_NAME=Design Hub`.
Existing production mail settings are extended in place. A conflicting value
causes deployment to fail rather than being silently replaced.

The production API image is rebuilt and restarted after automated tests pass.
Postfix, OpenDKIM, private Docker networking, SPF, DKIM, DMARC, and PTR remain
unchanged.

## Error Handling

Invalid sender addresses or blank display names fail during application
composition. Header generation errors propagate; the mailer does not replace
invalid values with defaults. SMTP network errors retain the existing
password-reset behavior: the generated reset challenge is invalidated and the
request fails.

## Automated Verification

Tests capture the actual `EmailMessage` handed to the SMTP boundary and assert:

- the branded `From` address parses to the configured display name and address;
- `Date` parses as an aware timestamp;
- `Message-ID` is syntactically valid, uses `image.sepaitech.com`, and differs
  between two messages;
- `Auto-Submitted` is exactly `auto-generated`;
- SMTP mode rejects a blank sender display name;
- deployment examples and provisioning include the fixed production value.

The complete backend test suite and Ruff checks must pass before deployment.

## Production Acceptance

After deployment:

1. Verify API, SMTP, and OpenDKIM containers are healthy and the queue is empty.
2. Send a branded infrastructure test to `zhaok157@gmail.com` and confirm Gmail
   accepts it.
3. Confirm that `zhaok157@gmail.com` already belongs to an application account.
   If it does not, stop and ask before creating any account.
4. Request password reset through the public `/api/auth/forgot-password`
   endpoint.
5. Obtain the received verification code from the user or from Gmail only after
   the user explicitly authorizes browser access to that message.
6. Before submitting the reset, obtain the user's chosen new password or
   approval to generate one. Do not print it in logs or commit it.
7. Submit `/api/auth/reset-password`, then verify login with the new password.
8. Confirm the reset challenge cannot be reused and the Postfix queue is empty.

Gmail inbox placement is observed separately from SMTP acceptance. SPF, DKIM,
and DMARC results are checked from Gmail's original-message authentication
summary when available.

## Rollback

Application rollback uses the pre-deployment API image. No database migration
is required. Reverting the application image restores the previous header
behavior without changing DNS or mail-service state.
