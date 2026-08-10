#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_source="$(cd "$script_dir/.." && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fixture_repo="$tmp_dir/repo"
remote_root="$tmp_dir/remote"
fake_bin="$tmp_dir/bin"
runtime_log="$tmp_dir/runtime.log"
runtime_fail_once="$tmp_dir/fail-live-once"
mkdir -p "$fixture_repo/image-code" "$fixture_repo/image-web" "$fake_bin"
printf 'backend release fixture\n' > "$fixture_repo/image-code/app.txt"

cat > "$fake_bin/npm" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == "run build" ]]; then
  mkdir -p dist
  printf '<html>versioned fixture</html>\n' > dist/index.html
fi
SH
chmod +x "$fake_bin/npm"

cat > "$tmp_dir/fake-runtime.sh" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
action="$1"
release_dir="$2"
release_id="$3"
printf '%s:%s\n' "$action" "$release_id" >> "$RUNTIME_LOG"
case "$action" in
  import-legacy)
    ;;
  backup-database)
    mkdir -p "$BACKUP_DIR"
    printf '%s\n' 'fixture database backup' > "$BACKUP_DIR/$release_id.sql"
    ;;
  health-live)
    if [[ -f "$RUNTIME_FAIL_ONCE" ]]; then
      rm -f "$RUNTIME_FAIL_ONCE"
      exit 42
    fi
    ;;
  restore-schema)
    [[ -s "$4" ]]
    ;;
  prepare|build-release|enable-maintenance|migrate|start-release|health-candidate|switch-web|health-public)
    ;;
  *)
    echo "unexpected runtime action: $action" >&2
    exit 2
    ;;
esac
SH
chmod +x "$tmp_dir/fake-runtime.sh"

stage_release() {
  local release_id="$1"
  REPO_ROOT="$fixture_repo" \
  DEPLOY_SOURCE_DIR="$deploy_source" \
  DEPLOY_LOCAL_ROOT="$remote_root" \
  RELEASE_ID="$release_id" \
  NPM_BIN="$fake_bin/npm" \
    bash "$script_dir/push.sh"
}

stage_release release-a
[[ -f "$remote_root/releases/release-a/app/app.txt" ]]
[[ -f "$remote_root/releases/release-a/web/index.html" ]]
[[ -f "$remote_root/releases/release-a/deploy/compose.yml" ]]
[[ -f "$remote_root/releases/release-a/release.env" ]]
[[ ! -e "$remote_root/web" ]]
[[ ! -e "$remote_root/app" ]]
if stage_release release-a >/dev/null 2>&1; then
  echo "ERROR: immutable release identifier was overwritten" >&2
  exit 1
fi

mkdir -p "$remote_root/web" "$remote_root/state" "$remote_root/backups"
printf '<html>legacy live</html>\n' > "$remote_root/web/index.html"
legacy_value="abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789"
cat > "$remote_root/.env" <<ENV
DB_URL=mysql+aiomysql://root:fixture@mysql:3306/design_hub
REDIS_PASSWORD=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
REDIS_URL=redis://:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef@redis:6379/0
MAIL_DELIVERY_MODE=smtp
SMTP_HOST=smtp
SMTP_PORT=25
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM_NAME=Design Hub
SMTP_FROM=no-reply@image.sepaitech.com
SMTP_USE_TLS=false
PASSWORD_RESET_CODE_PEPPER=${legacy_value}
ENV
chmod 600 "$remote_root/.env"

touch "$runtime_fail_once"
failed_release_log="$tmp_dir/failed-release.log"
if DEPLOY_ROOT="$remote_root" \
  DATA_DIR="$tmp_dir/data" \
  BACKUP_DIR="$remote_root/backups" \
  RELEASE_RUNTIME="$tmp_dir/fake-runtime.sh" \
  RUNTIME_LOG="$runtime_log" \
  RUNTIME_FAIL_ONCE="$runtime_fail_once" \
    bash "$remote_root/releases/release-a/deploy/scripts/deploy.sh" release-a \
      > "$failed_release_log" 2>&1; then
  echo "ERROR: failed live health check did not fail the release" >&2
  exit 1
fi
grep -q 'failed; restoring legacy-' "$failed_release_log"

legacy_release="$(cat "$remote_root/state/active-release")"
[[ "$legacy_release" == legacy-* ]]
[[ ! -e "$remote_root/state/maintenance" ]]
grep -q '^PASSWORD_RESET_CODE_PEPPER=' "$remote_root/shared/.env"
! grep -q '^EMAIL_VERIFICATION_CODE_PEPPER=' "$remote_root/shared/.env"
grep -q "start-release:${legacy_release}" "$runtime_log"
! grep -q '^restore-schema:' "$runtime_log"

stage_release release-b
DEPLOY_ROOT="$remote_root" \
DATA_DIR="$tmp_dir/data" \
BACKUP_DIR="$remote_root/backups" \
RELEASE_RUNTIME="$tmp_dir/fake-runtime.sh" \
RUNTIME_LOG="$runtime_log" \
RUNTIME_FAIL_ONCE="$runtime_fail_once" \
  bash "$remote_root/releases/release-b/deploy/scripts/deploy.sh" release-b

[[ "$(cat "$remote_root/state/active-release")" == "release-b" ]]
[[ "$(cat "$remote_root/state/previous-release")" == "$legacy_release" ]]
[[ ! -e "$remote_root/state/maintenance" ]]
! grep -q '^PASSWORD_RESET_CODE_PEPPER=' "$remote_root/shared/.env"
grep -q '^EMAIL_VERIFICATION_CODE_PEPPER=' "$remote_root/shared/.env"

DEPLOY_ROOT="$remote_root" \
DATA_DIR="$tmp_dir/data" \
BACKUP_DIR="$remote_root/backups" \
RELEASE_RUNTIME="$tmp_dir/fake-runtime.sh" \
RUNTIME_LOG="$runtime_log" \
RUNTIME_FAIL_ONCE="$runtime_fail_once" \
  bash "$remote_root/releases/release-b/deploy/scripts/rollback.sh" \
    --from release-b --to "$legacy_release"

[[ "$(cat "$remote_root/state/active-release")" == "$legacy_release" ]]
grep -q '^PASSWORD_RESET_CODE_PEPPER=' "$remote_root/shared/.env"
! grep -q '^EMAIL_VERIFICATION_CODE_PEPPER=' "$remote_root/shared/.env"
! grep -q '^restore-schema:' "$runtime_log"

schema_backup="$tmp_dir/explicit-schema.sql"
printf '%s\n' 'explicit schema rollback fixture' > "$schema_backup"
DEPLOY_ROOT="$remote_root" \
DATA_DIR="$tmp_dir/data" \
BACKUP_DIR="$remote_root/backups" \
RELEASE_RUNTIME="$tmp_dir/fake-runtime.sh" \
RUNTIME_LOG="$runtime_log" \
RUNTIME_FAIL_ONCE="$runtime_fail_once" \
  bash "$remote_root/releases/release-b/deploy/scripts/rollback.sh" \
    --from release-b --to "$legacy_release" --schema-backup "$schema_backup"
grep -q "restore-schema:${legacy_release}" "$runtime_log"

echo "versioned release, automatic rollback, environment restore, and explicit schema rollback: OK"
