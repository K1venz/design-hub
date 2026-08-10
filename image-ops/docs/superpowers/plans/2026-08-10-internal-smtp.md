# Internal SMTP Delivery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Deploy a private Postfix/OpenDKIM delivery service for `no-reply@image.sepaitech.com`, connect password reset to it, and fail safely when SMTP submission fails.

**Architecture:** Add separate Postfix and OpenDKIM containers on a dedicated Compose network with a persistent queue and DKIM key. Move mailer selection into the composition root with an explicit `smtp|log` mode, use a dedicated reset-code pepper, and invalidate a newly-created challenge when SMTP submission fails.

**Tech Stack:** Python 3.12, FastAPI, Pydantic Settings, pytest, Docker Compose, Debian stable slim, Postfix, OpenDKIM, Bash.

## Global Constraints

- Sender is exactly `no-reply@image.sepaitech.com`.
- SMTP hostname is exactly `smtp.image.sepaitech.com`.
- DKIM domain is `image.sepaitech.com`; selector is `designhub`; RSA key size is 2048 bits.
- SMTP port 25 is exposed only inside Docker and is never published on the host.
- Only `172.29.0.0/24` is trusted for relay; current server networks use `172.17.0.0/16` through `172.20.0.0/16`.
- Mail queue and DKIM material live below `/data/docker/design-hub/mail`.
- No private key, password, reset code, or full reset-code hash may be logged or committed.
- Existing unrelated untracked file `scripts/server-probe.ps1` must remain untouched.
- Every task follows red-green-refactor and ends in its own commit.

---

## File Map

- `image-code/src/design_hub/config/settings.py`: validate explicit mail mode and SMTP/reset-pepper requirements.
- `image-code/src/design_hub/composition.py`: build the selected mail adapter.
- `image-code/src/design_hub/interface/api/asgi.py`: consume the composition function and dedicated pepper.
- `image-code/src/design_hub/infrastructure/mail/logging_mailer.py`: emit metadata only, never the message body.
- `image-code/src/design_hub/application/auth/account_service.py`: invalidate a new challenge when submission fails.
- `image-code/tests/test_mail_composition.py`: settings, adapter selection, and redacted logging tests.
- `image-code/tests/test_auth.py`: SMTP failure and immediate retry behavior.
- `image-ops/deploy/mail/postfix/*`: Postfix image, configuration, and entrypoint.
- `image-ops/deploy/mail/opendkim/*`: OpenDKIM image, signing tables, configuration, and entrypoint.
- `image-ops/deploy/compose.yml`: SMTP/DKIM services, network, persistence, dependencies, and health checks.
- `image-ops/deploy/.env.example`: production mail environment contract.
- `image-ops/deploy/scripts/deploy.sh`: idempotent directories, secrets, key generation, startup, and validation.
- `image-ops/deploy/README.md`: operator workflow, DNS artifact, queue inspection, and rollback.

---

### Task 1: Explicit Mail Composition and Secret Separation

**Files:**

- Create: `image-code/tests/test_mail_composition.py`
- Modify: `image-code/src/design_hub/config/settings.py`
- Modify: `image-code/src/design_hub/composition.py`
- Modify: `image-code/src/design_hub/interface/api/asgi.py`
- Modify: `image-code/src/design_hub/infrastructure/mail/logging_mailer.py`

**Interfaces:**

- Consumes: existing `Settings`, `MailPort`, `LoggingMailer`, and `SmtpMailer`.
- Produces: `build_mailer(settings: Settings) -> MailPort`, `mail_delivery_mode: Literal["log", "smtp"]`, and `password_reset_code_pepper: SecretStr`.

- [ ] **Step 1: Write failing settings and composition tests**

```python
def test_smtp_mode_requires_host_from_and_pepper() -> None:
    with pytest.raises(ValidationError, match="SMTP_HOST"):
        Settings(_env_file=None, mail_delivery_mode="smtp")


def test_smtp_mode_builds_smtp_mailer() -> None:
    settings = Settings(
        _env_file=None,
        mail_delivery_mode="smtp",
        smtp_host="smtp",
        smtp_port=25,
        smtp_from="no-reply@image.sepaitech.com",
        smtp_use_tls=False,
        password_reset_code_pepper="pepper",
    )
    assert isinstance(build_mailer(settings), SmtpMailer)


def test_log_mode_does_not_log_mail_body(caplog: pytest.LogCaptureFixture) -> None:
    asyncio.run(
        LoggingMailer().send(
            to="user@example.com",
            subject="reset",
            body_text="验证码：123456",
        )
    )
    assert "123456" not in caplog.text
```

- [ ] **Step 2: Run the tests and verify red**

Run:

```powershell
cd D:\image-gen\image-code
uv run pytest tests/test_mail_composition.py -q
```

Expected: failures because the settings fields and `build_mailer` do not exist and the log currently includes the body.

- [ ] **Step 3: Implement the configuration contract**

Add to `Settings`:

```python
from typing import Literal

mail_delivery_mode: Literal["log", "smtp"] = "log"
password_reset_code_pepper: SecretStr = SecretStr("")
```

Extend the existing model validator:

```python
if self.mail_delivery_mode == "smtp":
    missing = [
        name
        for name, value in (
            ("SMTP_HOST", self.smtp_host.strip()),
            ("SMTP_FROM", self.smtp_from.strip()),
            (
                "PASSWORD_RESET_CODE_PEPPER",
                self.password_reset_code_pepper.get_secret_value(),
            ),
        )
        if not value
    ]
    if missing:
        raise ValueError(f"SMTP mail delivery requires: {', '.join(missing)}")
```

- [ ] **Step 4: Move mail adapter selection into the composition root**

Add to `composition.py`:

```python
def build_mailer(settings: Settings) -> MailPort:
    if settings.mail_delivery_mode == "log":
        return LoggingMailer()
    return SmtpMailer(
        host=settings.smtp_host.strip(),
        port=settings.smtp_port,
        username=settings.smtp_username,
        password=settings.smtp_password.get_secret_value(),
        from_addr=settings.smtp_from.strip(),
        use_tls=settings.smtp_use_tls,
    )
```

Replace the conditional mailer construction in `asgi.py` with `build_mailer(settings)`, and pass `settings.password_reset_code_pepper.get_secret_value()` to `AccountService`.

- [ ] **Step 5: Redact log-mode content**

Change `LoggingMailer.send` to log only:

```python
log.info("mail.delivery_skipped", to=to, subject=subject, body_bytes=len(body_text.encode()))
```

- [ ] **Step 6: Run targeted and regression tests**

```powershell
cd D:\image-gen\image-code
uv run pytest tests/test_mail_composition.py tests/test_auth.py tests/test_process_composition.py -q
```

Expected: all pass.

- [ ] **Step 7: Commit**

```powershell
git add image-code/src/design_hub/config/settings.py image-code/src/design_hub/composition.py image-code/src/design_hub/interface/api/asgi.py image-code/src/design_hub/infrastructure/mail/logging_mailer.py image-code/tests/test_mail_composition.py
git commit -m "refactor: make mail delivery explicit" -m "Require complete SMTP configuration in smtp mode, use a dedicated password-reset pepper, centralize adapter composition, and prevent reset codes from appearing in log-mode output."
```

---

### Task 2: Invalidate Challenges After SMTP Submission Failure

**Files:**

- Modify: `image-code/tests/test_auth.py`
- Modify: `image-code/src/design_hub/application/auth/account_service.py`

**Interfaces:**

- Consumes: `PasswordResetStore.replace_active(...) -> PasswordResetChallenge` and `consume(challenge_id: str) -> None`.
- Produces: a request flow in which an SMTP exception leaves no active challenge and an immediate retry is not blocked by cooldown.

- [ ] **Step 1: Add a failing mailer and test**

```python
class _FailingMailer(MailPort):
    async def send(self, *, to: str, subject: str, body_text: str) -> None:
        raise OSError("smtp unavailable")


def test_forgot_password_mail_failure_invalidates_challenge() -> None:
    client, cipher, _, users, _, resets = _client(mailer=_FailingMailer())
    # Register a real enabled account, then request reset twice.
    first = client.post("/auth/forgot-password", json={"email": "mailfail@x.com"})
    second = client.post("/auth/forgot-password", json={"email": "mailfail@x.com"})
    assert first.status_code == 500
    assert second.status_code == 500
    assert asyncio.run(resets.get_active("mailfail@x.com")) is None
```

Refactor `_client` to accept an optional `MailPort` while preserving its existing default fake mailer.

- [ ] **Step 2: Run the failing test**

```powershell
cd D:\image-gen\image-code
uv run pytest tests/test_auth.py::test_forgot_password_mail_failure_invalidates_challenge -q
```

Expected: the second request is rejected by cooldown or an active challenge remains.

- [ ] **Step 3: Implement cleanup around SMTP submission**

```python
challenge = await self.resets.replace_active(
    email=email,
    code_hash=code_hash,
    expires_at=expires_at,
)
try:
    await self.mailer.send(...)
except Exception:
    await self.resets.consume(challenge.id)
    raise
```

Do not catch or downgrade the final error. Cleanup failure is allowed to propagate because it means reset state is unknown.

- [ ] **Step 4: Run auth tests**

```powershell
cd D:\image-gen\image-code
uv run pytest tests/test_auth.py -q
```

Expected: all pass.

- [ ] **Step 5: Commit**

```powershell
git add image-code/src/design_hub/application/auth/account_service.py image-code/tests/test_auth.py
git commit -m "fix: clear failed password reset deliveries" -m "Consume a newly-created reset challenge when SMTP submission fails so users can retry immediately and are not blocked by a code they never received."
```

---

### Task 3: Build the Postfix and OpenDKIM Services

**Files:**

- Create: `image-ops/deploy/mail/postfix/Dockerfile`
- Create: `image-ops/deploy/mail/postfix/entrypoint.sh`
- Create: `image-ops/deploy/mail/postfix/main.cf.template`
- Create: `image-ops/deploy/mail/opendkim/Dockerfile`
- Create: `image-ops/deploy/mail/opendkim/entrypoint.sh`
- Create: `image-ops/deploy/mail/opendkim/opendkim.conf`
- Create: `image-ops/deploy/mail/opendkim/KeyTable`
- Create: `image-ops/deploy/mail/opendkim/SigningTable`
- Create: `image-ops/deploy/mail/opendkim/TrustedHosts`
- Modify: `image-ops/deploy/compose.yml`

**Interfaces:**

- Consumes: `MAIL_HOSTNAME`, `MAIL_DOMAIN`, `MAIL_NETWORKS`, and the mounted `designhub.private` key.
- Produces: `smtp:25`, `dkim:8891`, persistent `/var/spool/postfix`, and healthy Compose services.

- [ ] **Step 1: Add a static infrastructure assertion script**

Create `image-ops/deploy/scripts/check-mail-config.sh` with assertions that:

```bash
docker compose config >/dev/null
docker compose config | grep -q '172.29.0.0/24'
! docker compose config | grep -A20 'smtp:' | grep -q 'published:'
grep -q 'reject_unauth_destination' mail/postfix/main.cf.template
grep -q 'designhub._domainkey.image.sepaitech.com' mail/opendkim/KeyTable
```

- [ ] **Step 2: Run the check and verify red**

Run in WSL or on the Linux server checkout:

```bash
cd /opt/docker/design-hub
bash scripts/check-mail-config.sh
```

Expected: fail because the services and files do not exist.

- [ ] **Step 3: Create the Postfix image**

The Dockerfile uses `debian:stable-slim`, installs `postfix`, `ca-certificates`, `gettext-base`, `netcat-openbsd`, and `tini`, copies the entrypoint/template, and starts with `tini`.

The rendered `main.cf` must include:

```ini
myhostname = ${MAIL_HOSTNAME}
myorigin = ${MAIL_DOMAIN}
inet_interfaces = all
inet_protocols = ipv4
mynetworks = 127.0.0.0/8, ${MAIL_NETWORKS}
smtpd_client_restrictions = permit_mynetworks, reject
smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination
smtpd_recipient_restrictions = permit_mynetworks, reject_unauth_destination
smtpd_milters = inet:dkim:8891
non_smtpd_milters = inet:dkim:8891
milter_default_action = tempfail
smtp_tls_security_level = may
smtp_tls_CApath = /etc/ssl/certs
message_size_limit = 10485760
smtpd_recipient_limit = 20
```

The entrypoint validates all three required environment variables, renders with `envsubst`, runs `postfix set-permissions` and `postfix check`, then executes `postfix start-fg`.

- [ ] **Step 4: Create the OpenDKIM image**

Install `opendkim`, `opendkim-tools`, `netcat-openbsd`, and `tini`. Configure:

```text
Mode                    s
Canonicalization        relaxed/simple
Socket                  inet:8891@0.0.0.0
KeyTable                file:/etc/opendkim/KeyTable
SigningTable            refile:/etc/opendkim/SigningTable
InternalHosts           file:/etc/opendkim/TrustedHosts
ExternalIgnoreList      file:/etc/opendkim/TrustedHosts
```

Tables are exact:

```text
# KeyTable
designhub._domainkey.image.sepaitech.com image.sepaitech.com:designhub:/etc/dkimkeys/designhub.private

# SigningTable
*@image.sepaitech.com designhub._domainkey.image.sepaitech.com

# TrustedHosts
127.0.0.1
172.29.0.0/24
```

The entrypoint rejects a missing/empty key, sets key ownership/mode inside the container, validates configuration with `opendkim -n`, and starts `opendkim -f`.

- [ ] **Step 5: Extend Compose**

Add `mail` network with subnet `172.29.0.0/24`. Attach API, smtp, and dkim only. Define:

```yaml
dkim:
  build: ./mail/opendkim
  volumes:
    - /data/docker/design-hub/mail/dkim:/etc/dkimkeys
  expose: ["8891"]

smtp:
  build: ./mail/postfix
  environment:
    MAIL_HOSTNAME: smtp.image.sepaitech.com
    MAIL_DOMAIN: image.sepaitech.com
    MAIL_NETWORKS: 172.29.0.0/24
  volumes:
    - /data/docker/design-hub/mail/spool:/var/spool/postfix
  expose: ["25"]
  depends_on:
    dkim:
      condition: service_healthy
```

Add resource limits and health checks. Make API depend on healthy smtp as well as Redis.

- [ ] **Step 6: Run static and container configuration checks**

```bash
cd image-ops/deploy
bash scripts/check-mail-config.sh
docker compose build dkim smtp
docker compose run --rm --no-deps --entrypoint opendkim dkim -n -x /etc/opendkim.conf
```

Expected: all pass after a test key is mounted in a temporary deployment data directory.

- [ ] **Step 7: Commit**

```powershell
git add image-ops/deploy/compose.yml image-ops/deploy/mail image-ops/deploy/scripts/check-mail-config.sh
git commit -m "feat: add private SMTP delivery services" -m "Add isolated Postfix and OpenDKIM containers with relay restrictions, persistent queue and key mounts, fixed network boundaries, and health checks for password-reset delivery."
```

---

### Task 4: Make Deployment Idempotent and Document Operations

**Files:**

- Modify: `image-ops/deploy/.env.example`
- Modify: `image-ops/deploy/scripts/deploy.sh`
- Modify: `image-ops/deploy/README.md`

**Interfaces:**

- Consumes: the Task 3 Compose services and `/data/docker/design-hub/mail` paths.
- Produces: stable secrets, stable DKIM identity, root-only `dns-records.txt`, and repeatable SMTP deployment.

- [ ] **Step 1: Extend the static check with deployment assertions**

Require the environment example and deploy script to contain all of:

```text
MAIL_DELIVERY_MODE=smtp
SMTP_HOST=smtp
SMTP_PORT=25
SMTP_FROM=no-reply@image.sepaitech.com
SMTP_USE_TLS=false
PASSWORD_RESET_CODE_PEPPER
opendkim-genkey
dns-records.txt
```

- [ ] **Step 2: Run the check and verify red**

```bash
cd image-ops/deploy
bash scripts/check-mail-config.sh
```

Expected: fail on missing environment and deployment entries.

- [ ] **Step 3: Add the environment contract**

Add the exact non-secret values above to `.env.example`. Represent generated secrets with the repository convention `__GENERATED_64_HEX__`.

- [ ] **Step 4: Add idempotent mail provisioning**

Implement `ensure_mail_env` and `ensure_dkim_key` in `deploy.sh`:

```bash
ensure_env_value MAIL_DELIVERY_MODE smtp
ensure_env_value SMTP_HOST smtp
ensure_env_value SMTP_PORT 25
ensure_env_value SMTP_FROM no-reply@image.sepaitech.com
ensure_env_value SMTP_USE_TLS false
ensure_generated_hex PASSWORD_RESET_CODE_PEPPER 32
```

Create mail directories with `umask 077`. Generate the key only when `designhub.private` is absent:

```bash
docker compose run --rm --no-deps --entrypoint opendkim-genkey dkim \
  -b 2048 -d image.sepaitech.com -D /etc/dkimkeys -s designhub
```

Normalize the generated TXT record into `/data/docker/design-hub/mail/dns-records.txt`, set mode 600, and never print the private key.

- [ ] **Step 5: Integrate startup order**

Build all images, start `dkim`, wait healthy, start `smtp`, wait healthy, run an internal SMTP EHLO probe, then continue the existing migration and API/Worker/nginx startup sequence.

- [ ] **Step 6: Document operations**

Add commands for:

```bash
docker compose ps dkim smtp
docker exec design-hub-smtp postqueue -p
docker logs --since 30m design-hub-smtp
cat /data/docker/design-hub/mail/dns-records.txt
docker compose stop smtp dkim
```

Document the exact A/SPF/DKIM/DMARC/PTR records and state that external completion is blocked until public DNS verifies them.

- [ ] **Step 7: Run checks and commit**

```bash
cd image-ops/deploy
bash -n scripts/deploy.sh
bash scripts/check-mail-config.sh
docker compose config >/dev/null
```

```powershell
git add image-ops/deploy/.env.example image-ops/deploy/scripts/deploy.sh image-ops/deploy/README.md image-ops/deploy/scripts/check-mail-config.sh
git commit -m "feat: provision SMTP delivery idempotently" -m "Generate stable reset and DKIM secrets, start mail services before the API, produce operator DNS records, and document queue inspection and rollback without exposing sensitive values."
```

---

### Task 5: Full Local Verification

**Files:** No new production files; fix only failures caused by Tasks 1–4.

- [ ] **Step 1: Run Python quality gates**

```powershell
cd D:\image-gen\image-code
uv run pytest tests/test_mail_composition.py tests/test_auth.py tests/test_process_composition.py -q
uv run pytest -q
```

Expected: all tests pass.

- [ ] **Step 2: Run frontend regression gates**

```powershell
cd D:\image-gen\image-web
npm test -- --run
npm run build
```

Expected: all tests pass and production build succeeds.

- [ ] **Step 3: Run repository and infrastructure checks**

```powershell
cd D:\image-gen
git diff --check
git status --short
```

Run the Linux-only checks on the target server checkout before mutation:

```bash
cd /opt/docker/design-hub
bash -n scripts/deploy.sh
bash scripts/check-mail-config.sh
docker compose config >/dev/null
```

Expected: only the known untracked `scripts/server-probe.ps1` remains outside committed work.

---

### Task 6: Deploy and Verify on the Server

**Files:** Server state under `/opt/docker/design-hub` and `/data/docker/design-hub/mail`.

- [ ] **Step 1: Capture rollback state**

Via SSH, record container health, image IDs, current Alembic revision, and a redacted list of `.env` keys. Back up `.env` and Compose with timestamped root-only files. Tag the current API image with a timestamped rollback tag.

- [ ] **Step 2: Transfer committed artifacts**

Use the existing deployment sync behavior, but authenticate with the authorized password credential through Posh-SSH/SFTP because the documented local key is absent. Transfer `image-code`, `image-ops/deploy`, and the already-built frontend dist without deleting server `.env`, certificates, or persistent data.

- [ ] **Step 3: Run preflight checks remotely**

```bash
cd /opt/docker/design-hub
bash -n scripts/deploy.sh
bash scripts/check-mail-config.sh
docker compose config >/dev/null
```

Stop immediately on failure.

- [ ] **Step 4: Run deployment**

```bash
cd /opt/docker/design-hub
bash scripts/deploy.sh
```

The script performs DB backup/migration and starts dkim, smtp, redis, api, worker, and nginx.

- [ ] **Step 5: Verify internal SMTP and application health**

```bash
docker compose ps
docker exec design-hub-smtp postconf myhostname mynetworks smtpd_relay_restrictions
docker exec design-hub-smtp postqueue -p
ss -lntp | grep -E ':(25|465|587) ' && exit 1 || true
docker logs --since 10m design-hub-dkim
docker logs --since 10m design-hub-smtp
```

Submit a probe message from the API container using Python `smtplib` to `smtp:25`; verify Postfix assigns a queue ID and OpenDKIM adds `DKIM-Signature` before delivery.

- [ ] **Step 6: Produce DNS handoff**

Read only `/data/docker/design-hub/mail/dns-records.txt` and report these non-secret DNS values to the user:

- `smtp.image.sepaitech.com A 14.103.51.191`
- `image.sepaitech.com TXT v=spf1 ip4:14.103.51.191 -all`
- generated `designhub._domainkey.image.sepaitech.com` TXT
- `_dmarc.image.sepaitech.com TXT v=DMARC1; p=none`
- `14.103.51.191 PTR smtp.image.sepaitech.com`

- [ ] **Step 7: Verify public records and end-to-end reset after DNS propagation**

Query public resolvers for A, SPF, DKIM, DMARC, and PTR. Then request a reset for a user-controlled real mailbox, confirm receipt, inspect Authentication-Results for SPF/DKIM/DMARC pass, and complete the password reset.

If DNS/PTR is not yet configured, mark only external delivery verification as pending; do not claim the entire feature complete.
