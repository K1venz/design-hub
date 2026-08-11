# Design Hub production release and mail operations

The production stack contains the versioned SPA, FastAPI API, generation worker,
Redis, Postfix, OpenDKIM, nginx, and the existing MySQL 8.4 service. Transactional
mail uses the private Docker SMTP network and the identity
`Design Hub <no-reply@image.sepaitech.com>`.

## Release layout

`push.sh` never writes the live application or web mount. It uploads a complete
candidate to `.incoming/<release-id>` and finalizes it with a same-filesystem
rename only after the API source, SPA index, compose file, and release manifest
are present.

```text
/opt/docker/design-hub/
├── .incoming/                    # incomplete uploads; never served
├── releases/<release-id>/
│   ├── app/                      # immutable API build context
│   ├── web/                      # immutable SPA build
│   ├── deploy/                   # compose, nginx, mail, release scripts
│   └── release.env               # ID, source commit, SPA index hash; no secrets
├── shared/
│   ├── .env                      # production environment, mode 600
│   └── nginx/certs/
├── state/
│   ├── active-release
│   ├── previous-release
│   ├── pending-release            # exists only while a candidate is uncommitted
│   ├── maintenance               # presence makes HTTPS return 503
│   ├── env-snapshots/<release>.before.env
│   └── env-snapshots/<release>.before.meta

/root/db-backup-<release>-<timestamp>.sql

/data/docker/design-hub/
├── redis/
├── generated/
├── assets/
├── exports/
└── mail/{spool,dkim}/
```

The API and worker image is tagged `design-hub-api:<release-id>` and is never
rebuilt under an existing identity. Compose labels API, worker, and nginx with
the same release ID. nginx binds only `releases/<release-id>/web` selected by the
release orchestrator.

## Staging and deploying

From the repository root:

```bash
RELEASE_ID="$(git rev-parse --short=12 HEAD)-$(date -u +%Y%m%dT%H%M%SZ)"
RELEASE_ID="$RELEASE_ID" bash image-ops/deploy/scripts/push.sh
```

The script always runs a clean frontend build, stages the three release parts,
and prints the immutable release ID. Then run that release's orchestrator on the
server:

```bash
bash /opt/docker/design-hub/releases/<release-id>/deploy/scripts/deploy.sh <release-id>
```

The orchestrator performs these guarded steps:

1. On the first release-managed rollout, import the existing SPA and
   `design-hub-api:latest` as an immutable `legacy-*` rollback release.
2. Copy the existing root `.env` into `shared/.env` when needed and create a
   mode-600 snapshot plus non-secret metadata that binds its SHA-256 digest to
   the candidate and rollback-target release identities. Record the candidate
   as pending before any environment mutation.
3. Explicitly and atomically rename `PASSWORD_RESET_CODE_PEPPER` to
   `EMAIL_VERIFICATION_CODE_PEPPER` without printing values. Normal provisioning
   rejects the legacy key; only this migration path accepts it.
4. Validate Redis/mail settings, compose semantics, certificates, DKIM material,
   and the database connection; build the immutable candidate image.
5. Create `state/maintenance` and recreate nginx with the maintenance-aware
   configuration before any database or runtime switch.
6. Back up MySQL, run Alembic from the candidate image, start API/worker, and
   require container, API, and migration health.
7. Recreate nginx against the versioned SPA while the prior release remains
   active in state, verify its index hash, remove maintenance, and check the
   public endpoint. Only then atomically promote the pending candidate to active.

Any failure after the environment snapshot automatically invokes the executable
rollback path. If rollback itself fails, maintenance remains enabled and the
script exits nonzero.

## Environment and mail boundary

Production uses:

```text
MAIL_DELIVERY_MODE=smtp
SMTP_HOST=smtp
SMTP_PORT=25
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_NAME=Design Hub
SMTP_FROM=no-reply@image.sepaitech.com
SMTP_USE_TLS=false
EMAIL_VERIFICATION_CODE_PEPPER=<64 lowercase hexadecimal characters>
```

The pepper is independent from the JWT secret and uses purpose-separated HMAC
inputs for registration and password reset. `SMTP_FROM` is a strict mailbox;
missing local parts, whitespace, display-name syntax, and CRLF are rejected at
settings construction.

The `mail` network is `172.29.0.0/24`. Postfix is `172.29.0.10`, OpenDKIM is
`172.29.0.11`, and neither publishes a host port. Only the API joins this network;
worker, nginx, and Redis cannot submit mail. OpenDKIM private keys stay under
`/data/docker/design-hub/mail/dkim`.

## Registration contract rollout

The SPA and API switch as one release. Register/resend acknowledgements carry an
opaque challenge ID; verify and resend require it. The browser stores email plus
challenge ID only in memory and replaces the ID after resend. Serving a new SPA
against an old API is prevented by staging, maintenance, candidate health, and
the controlled nginx web recreation.

General smoke tests log in with runtime-provided pre-verified accounts and do not
send mail. The separate interactive registration acceptance script obtains the
recipient, approved password, and received code at runtime.

## Rollback

Normal rollback changes the API/worker image, versioned SPA, and bound
environment snapshot together. It verifies that `--from` is active, `--to` is
the recorded previous release, and the snapshot metadata binds that exact edge.
It deliberately does not restore the database:

```bash
bash /opt/docker/design-hub/releases/<from-release>/deploy/scripts/rollback.sh \
  --from <from-release> \
  --to <previous-release>
```

Only an explicitly required schema rollback may restore a database backup:

```bash
bash /opt/docker/design-hub/releases/<from-release>/deploy/scripts/rollback.sh \
  --from <from-release> \
  --to <previous-release> \
  --schema-backup /root/db-backup-<release>.sql
```

The rollback command enables maintenance first and restores the verified
mode-600 environment snapshot. Runtime-only rollback then starts and
health-checks the previous immutable API/worker without a database restore. An
explicit schema restore first stops API and worker and verifies both are stopped
before importing MySQL. Both paths recreate nginx against the previous SPA and
only remove maintenance for the public probe window; any failure restores the
marker atomically. DNS, SMTP queue, DKIM keys, and other persisted application
data are not deleted.

## Validation

Local release semantics and environment restoration are executable tests:

```bash
bash image-ops/deploy/scripts/test-mail-env.sh
bash image-ops/deploy/scripts/test-registration-ratelimits.sh
bash image-ops/deploy/scripts/test-release-flow.sh
bash image-ops/deploy/scripts/test-release-safety.sh
```

On the production host also run compose and nginx validation through the staged
release, then inspect service health and the mail queue:

```bash
docker compose ps
docker exec design-hub-nginx nginx -t
docker exec design-hub-smtp postqueue -p
```

## DNS and network ports

The deployment-generated DNS checklist remains at
`/data/docker/design-hub/mail/dns-records.txt`. Publish A, SPF, DKIM, DMARC, and
provider-managed PTR records described there. Public ingress requires only
22/80/443. SMTP needs outbound TCP 25; ports 25, 3306, 6379, 8000, and 8891 are
not published by this stack.
