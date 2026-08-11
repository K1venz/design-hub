#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_source="${DEPLOY_SOURCE_UNDER_TEST:-$(cd "$script_dir/.." && pwd)}"
test_case="${TEST_CASE:-all}"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

fixture_repo="$tmp_dir/repo"
fake_bin="$tmp_dir/bin"
fake_runtime="$tmp_dir/fake-runtime.sh"
mkdir -p "$fixture_repo/image-code" "$fixture_repo/image-web" "$fake_bin"
printf 'backend release fixture\n' > "$fixture_repo/image-code/app.txt"

fail() {
  echo "ERROR: $*" >&2
  exit 1
}

assert_file_mode_600() {
  local path="$1"
  local actual_mode
  actual_mode="$(stat -c '%a' "$path")"
  [[ "$actual_mode" == 600 ]] || fail "${path} mode is ${actual_mode}, expected 600"
}

assert_before() {
  local log_file="$1"
  local earlier="$2"
  local later="$3"
  local earlier_line
  local later_line
  earlier_line="$(grep -n -m1 "^${earlier}:" "$log_file" | cut -d: -f1 || true)"
  later_line="$(grep -n -m1 "^${later}:" "$log_file" | cut -d: -f1 || true)"
  [[ -n "$earlier_line" ]] || fail "missing runtime action ${earlier}"
  [[ -n "$later_line" ]] || fail "missing runtime action ${later}"
  [[ "$earlier_line" -lt "$later_line" ]] || fail "${earlier} did not precede ${later}"
}

cat > "$fake_bin/npm" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$*" == "run build" ]]; then
  mkdir -p dist
  printf '<html>versioned fixture</html>\n' > dist/index.html
fi
SH
chmod +x "$fake_bin/npm"

cat > "$fake_runtime" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
action="${1:?runtime action is required}"
release_dir="${2:?release directory is required}"
release_id="${3:?release identifier is required}"
argument="${4:-}"
active="none"
pending="none"
maintenance="off"
[[ -f "$DEPLOY_ROOT/state/active-release" ]] && active="$(cat "$DEPLOY_ROOT/state/active-release")"
[[ -f "$DEPLOY_ROOT/state/pending-release" ]] && pending="$(cat "$DEPLOY_ROOT/state/pending-release")"
[[ -f "$DEPLOY_ROOT/state/maintenance" ]] && maintenance="on"
printf '%s:%s:active=%s:pending=%s:maintenance=%s\n' \
  "$action" "$release_id" "$active" "$pending" "$maintenance" >> "$RUNTIME_LOG"

if [[ -f "$RUNTIME_FAIL_ONCE" ]] \
  && [[ "$(head -1 "$RUNTIME_FAIL_ONCE")" == "${action}:${release_id}" ]]; then
  tail -n +2 "$RUNTIME_FAIL_ONCE" > "${RUNTIME_FAIL_ONCE}.next"
  if [[ -s "${RUNTIME_FAIL_ONCE}.next" ]]; then
    mv -f "${RUNTIME_FAIL_ONCE}.next" "$RUNTIME_FAIL_ONCE"
  else
    rm -f "$RUNTIME_FAIL_ONCE" "${RUNTIME_FAIL_ONCE}.next"
  fi
  exit 42
fi

case "$action" in
  import-legacy)
    ;;
  backup-database)
    mkdir -p "$BACKUP_DIR"
    printf '%s\n' 'fixture database backup' > "$BACKUP_DIR/$release_id.sql"
    ;;
  restore-schema)
    [[ -s "$argument" ]]
    ;;
  prepare|build-release|enable-maintenance|migrate|start-release|health-candidate|switch-web|health-live|health-public|stop-application|verify-application-stopped)
    ;;
  *)
    echo "unexpected runtime action: $action" >&2
    exit 2
    ;;
esac
SH
chmod +x "$fake_runtime"

selected() {
  [[ "$test_case" == all || "$test_case" == "$1" ]]
}

stage_release() {
  local remote_root="$1"
  local release_id="$2"
  REPO_ROOT="$fixture_repo" \
  DEPLOY_SOURCE_DIR="$deploy_source" \
  DEPLOY_LOCAL_ROOT="$remote_root" \
  RELEASE_ID="$release_id" \
  NPM_BIN="$fake_bin/npm" \
    bash "$script_dir/push.sh" >/dev/null
}

write_valid_environment() {
  local destination="$1"
  local sentinel="$2"
  cat > "$destination" <<ENV
TEST_SECRET_SENTINEL=${sentinel}
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
EMAIL_VERIFICATION_CODE_PEPPER=abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789
ENV
  chmod 600 "$destination"
}

prepare_active_legacy() {
  local remote_root="$1"
  local candidate="${2:-release-b}"
  mkdir -p "$remote_root/shared" "$remote_root/state" "$remote_root/backups"
  stage_release "$remote_root" release-a
  stage_release "$remote_root" "$candidate"
  sed -i 's/^SOURCE_COMMIT=.*/SOURCE_COMMIT=legacy-import/' \
    "$remote_root/releases/release-a/release.env"
  printf 'release-a\n' > "$remote_root/state/active-release"
  chmod 600 "$remote_root/state/active-release"
  write_valid_environment "$remote_root/shared/.env" "state-secret-${candidate}"
  : > "$remote_root/runtime.log"
}

set_runtime_failure() {
  local remote_root="$1"
  local action="$2"
  local release_id="$3"
  printf '%s:%s\n' "$action" "$release_id" > "$remote_root/fail-once"
}

set_runtime_failures() {
  local remote_root="$1"
  shift
  printf '%s\n' "$@" > "$remote_root/fail-once"
}

run_deploy() {
  local remote_root="$1"
  local release_id="$2"
  local log_file="$3"
  DEPLOY_ROOT="$remote_root" \
  DATA_DIR="$remote_root/data" \
  BACKUP_DIR="$remote_root/backups" \
  RELEASE_RUNTIME="$fake_runtime" \
  RUNTIME_LOG="$remote_root/runtime.log" \
  RUNTIME_FAIL_ONCE="$remote_root/fail-once" \
    bash "$remote_root/releases/$release_id/deploy/scripts/deploy.sh" "$release_id" \
      > "$log_file" 2>&1
}

run_rollback() {
  local remote_root="$1"
  local from_release="$2"
  local to_release="$3"
  local log_file="$4"
  shift 4
  DEPLOY_ROOT="$remote_root" \
  DATA_DIR="$remote_root/data" \
  BACKUP_DIR="$remote_root/backups" \
  RELEASE_RUNTIME="$fake_runtime" \
  RUNTIME_LOG="$remote_root/runtime.log" \
  RUNTIME_FAIL_ONCE="$remote_root/fail-once" \
  ROLLBACK_LOCK_HELD="${ROLLBACK_LOCK_HELD:-false}" \
    bash "$remote_root/releases/$from_release/deploy/scripts/rollback.sh" \
      --from "$from_release" --to "$to_release" "$@" > "$log_file" 2>&1
}

deploy_from_legacy() {
  local remote_root="$1"
  local candidate="${2:-release-b}"
  run_deploy "$remote_root" "$candidate" "$remote_root/deploy.log" \
    || fail "fixture deployment ${candidate} failed"
  [[ "$(cat "$remote_root/state/active-release")" == "$candidate" ]] \
    || fail "fixture deployment did not activate ${candidate}"
}

assert_environment_failure_restored() {
  local name="$1"
  local variant="$2"
  local remote_root="$tmp_dir/$name"
  local original="$remote_root/original.env"
  local deploy_log="$remote_root/deploy.log"
  local sentinel="secret-${name}-do-not-log"
  local legacy_pepper="fedcba9876543210fedcba9876543210fedcba9876543210fedcba9876543210"

  mkdir -p "$remote_root/shared" "$remote_root/state" "$remote_root/backups"
  stage_release "$remote_root" release-initial
  : > "$remote_root/runtime.log"
  case "$variant" in
    migrate)
      cat > "$remote_root/shared/.env" <<ENV
TEST_SECRET_SENTINEL=${sentinel}
PASSWORD_RESET_CODE_PEPPER=${legacy_pepper}
REDIS_PASSWORD=invalid
ENV
      ;;
    redis)
      cat > "$remote_root/shared/.env" <<ENV
TEST_SECRET_SENTINEL=${sentinel}
MAIL_DELIVERY_MODE=external
ENV
      ;;
    mail)
      cat > "$remote_root/shared/.env" <<ENV
TEST_SECRET_SENTINEL=${sentinel}
REDIS_PASSWORD=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
REDIS_URL=redis://:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef@redis:6379/0
ENV
      set_runtime_failure "$remote_root" prepare release-initial
      ;;
    *)
      fail "unknown environment failure variant ${variant}"
      ;;
  esac
  chmod 600 "$remote_root/shared/.env"
  cp "$remote_root/shared/.env" "$original"

  if run_deploy "$remote_root" release-initial "$deploy_log"; then
    fail "${name} unexpectedly succeeded"
  fi
  cmp -s "$original" "$remote_root/shared/.env" \
    || fail "${name} did not restore byte-identical environment"
  assert_file_mode_600 "$remote_root/shared/.env"
  assert_file_mode_600 "$remote_root/state/env-snapshots/release-initial.before.env"
  [[ ! -e "$remote_root/state/maintenance" ]] \
    || fail "${name} incorrectly left maintenance enabled before release work"
  [[ ! -e "$remote_root/state/pending-release" ]] \
    || fail "${name} left stale pending release state"
  ! grep -Fq "$sentinel" "$deploy_log" || fail "${name} leaked the environment secret"
  ! grep -Fq "$legacy_pepper" "$deploy_log" || fail "${name} leaked the legacy pepper"
}

test_initial_runtime_failure_restores_environment() {
  local remote_root="$tmp_dir/initial-runtime-failure"
  local original="$tmp_dir/initial-runtime-failure.before.env"
  local sentinel="secret-initial-runtime-do-not-log"
  mkdir -p "$remote_root/shared" "$remote_root/state" "$remote_root/backups"
  stage_release "$remote_root" release-initial
  cat > "$remote_root/shared/.env" <<ENV
TEST_SECRET_SENTINEL=${sentinel}
REDIS_PASSWORD=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
REDIS_URL=redis://:0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef@redis:6379/0
ENV
  cp "$remote_root/shared/.env" "$original"
  : > "$remote_root/runtime.log"
  set_runtime_failure "$remote_root" health-live release-initial

  if run_deploy "$remote_root" release-initial "$remote_root/deploy.log"; then
    fail "initial runtime health failure unexpectedly succeeded"
  fi
  cmp -s "$original" "$remote_root/shared/.env" \
    || fail "initial runtime failure did not restore byte-identical environment"
  assert_file_mode_600 "$remote_root/shared/.env"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "unrecoverable initial runtime failure did not retain maintenance"
  [[ "$(cat "$remote_root/state/pending-release")" == release-initial ]] \
    || fail "unrecoverable initial runtime failure lost pending state"
  [[ ! -e "$remote_root/state/active-release" ]] \
    || fail "failed initial release was recorded active"
  ! grep -Fq "$sentinel" "$remote_root/deploy.log" \
    || fail "initial runtime failure leaked an environment secret"
}

test_pending_state_and_snapshot_binding() {
  local remote_root="$tmp_dir/pending-state"
  local metadata
  local digest
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"

  grep -Eq '^health-public:release-b:active=release-a:pending=release-b:maintenance=off$' \
    "$remote_root/runtime.log" \
    || fail "public probe did not retain active target plus pending candidate state"
  [[ "$(cat "$remote_root/state/active-release")" == release-b ]]
  [[ "$(cat "$remote_root/state/previous-release")" == release-a ]]
  [[ ! -e "$remote_root/state/pending-release" ]] \
    || fail "successful deployment did not clear pending state"

  metadata="$remote_root/state/env-snapshots/release-b.before.meta"
  [[ -f "$metadata" ]] || fail "environment snapshot metadata is missing"
  assert_file_mode_600 "$metadata"
  grep -Fxq 'SNAPSHOT_FORMAT=1' "$metadata"
  grep -Fxq 'CANDIDATE_RELEASE=release-b' "$metadata"
  grep -Fxq 'ROLLBACK_RELEASE=release-a' "$metadata"
  digest="$(sha256sum "$remote_root/state/env-snapshots/release-b.before.env" | cut -d' ' -f1)"
  grep -Fxq "SNAPSHOT_SHA256=${digest}" "$metadata"
  ! grep -Fq 'state-secret-release-b' "$metadata" \
    || fail "snapshot metadata contains an environment secret"
}

test_stale_pending_deployment_rejected() {
  local remote_root="$tmp_dir/stale-pending"
  local before_env="$tmp_dir/stale-pending.before.env"
  prepare_active_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'other-candidate\n' > "$remote_root/state/pending-release"

  if run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then
    fail "deployment accepted stale pending release state"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "stale pending deployment mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "stale pending deployment invoked the runtime"
}

test_automatic_rollback_state_identity() {
  local remote_root="$tmp_dir/automatic-state"
  local before_env="$tmp_dir/automatic-state.before.env"
  prepare_active_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  set_runtime_failure "$remote_root" health-live release-b

  if run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then
    fail "failed candidate health unexpectedly succeeded"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "automatic rollback did not restore the environment"
  [[ "$(cat "$remote_root/state/active-release")" == release-a ]]
  [[ ! -e "$remote_root/state/pending-release" ]]
  [[ ! -e "$remote_root/state/maintenance" ]]
  grep -q '^start-release:release-a:' "$remote_root/runtime.log" \
    || fail "automatic rollback did not restart the rollback target"
  grep -q '^switch-web:release-a:' "$remote_root/runtime.log" \
    || fail "automatic rollback did not restore the target web release"
}

test_automatic_rollback_failure_is_safe() {
  local remote_root="$tmp_dir/automatic-rollback-failure"
  local before_env="$tmp_dir/automatic-rollback-failure.before.env"
  prepare_active_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  set_runtime_failures "$remote_root" \
    'health-live:release-b' 'start-release:release-a'

  if run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then
    fail "candidate plus automatic rollback failures unexpectedly succeeded"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "failed automatic rollback did not restore the environment"
  assert_file_mode_600 "$remote_root/shared/.env"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "failed automatic rollback did not retain maintenance"
  [[ "$(cat "$remote_root/state/active-release")" == release-a ]] \
    || fail "failed automatic rollback changed active release state"
  [[ "$(cat "$remote_root/state/pending-release")" == release-b ]] \
    || fail "failed automatic rollback lost pending candidate state"
  grep -q '^start-release:release-a:' "$remote_root/runtime.log" \
    || fail "automatic rollback failure fixture did not reach target restart"
  ! grep -q '^health-candidate:release-a:' "$remote_root/runtime.log" \
    || fail "automatic rollback continued after target restart failure"
  ! grep -Fq 'state-secret-release-b' "$remote_root/deploy.log" \
    || fail "automatic rollback failure leaked an environment secret"
}

test_manual_state_mismatch_rejected() {
  local remote_root="$tmp_dir/manual-state-mismatch"
  local before_env="$tmp_dir/manual-state-mismatch.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'release-a\n' > "$remote_root/state/active-release"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "manual rollback accepted a stale --from release"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "stale manual rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "stale manual rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "stale manual rollback failure did not enable maintenance"
}

test_manual_previous_mismatch_rejected() {
  local remote_root="$tmp_dir/manual-previous-mismatch"
  local before_env="$tmp_dir/manual-previous-mismatch.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'other-target\n' > "$remote_root/state/previous-release"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "manual rollback accepted a target other than recorded previous release"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "wrong-target manual rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "wrong-target manual rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "wrong-target manual rollback failure did not enable maintenance"
}

test_automatic_state_mismatch_rejected() {
  local remote_root="$tmp_dir/automatic-state-mismatch"
  local before_env="$tmp_dir/automatic-state-mismatch.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'release-a\n' > "$remote_root/state/active-release"
  printf 'other-candidate\n' > "$remote_root/state/pending-release"
  mkdir "$remote_root/state/deploy.lock"
  : > "$remote_root/runtime.log"

  if ROLLBACK_LOCK_HELD=true run_rollback \
    "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "automatic rollback accepted a mismatched pending candidate"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "mismatched automatic rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "mismatched automatic rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "mismatched automatic rollback failure did not enable maintenance"
}

test_automatic_active_mismatch_rejected() {
  local remote_root="$tmp_dir/automatic-active-mismatch"
  local before_env="$tmp_dir/automatic-active-mismatch.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'other-active\n' > "$remote_root/state/active-release"
  printf 'release-b\n' > "$remote_root/state/pending-release"
  mkdir "$remote_root/state/deploy.lock"
  : > "$remote_root/runtime.log"

  if ROLLBACK_LOCK_HELD=true run_rollback \
    "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "automatic rollback accepted a mismatched active rollback target"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "wrong-target automatic rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "wrong-target automatic rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "wrong-target automatic rollback failure did not enable maintenance"
}

test_snapshot_tamper_rejected() {
  local remote_root="$tmp_dir/snapshot-tamper"
  local before_env="$tmp_dir/snapshot-tamper.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'TAMPERED_SECRET=must-not-restore\n' \
    >> "$remote_root/state/env-snapshots/release-b.before.env"
  chmod 600 "$remote_root/state/env-snapshots/release-b.before.env"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "rollback accepted a tampered environment snapshot"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "tampered snapshot rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "tampered snapshot rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "tampered snapshot rollback failure did not enable maintenance"
}

test_cross_release_metadata_rejected() {
  local remote_root="$tmp_dir/cross-release"
  local snapshot
  local metadata
  local digest
  local before_env="$tmp_dir/cross-release.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  snapshot="$remote_root/state/env-snapshots/release-b.before.env"
  metadata="$remote_root/state/env-snapshots/release-b.before.meta"
  digest="$(sha256sum "$snapshot" | cut -d' ' -f1)"
  cat > "$metadata" <<ENV
SNAPSHOT_FORMAT=1
CANDIDATE_RELEASE=other-candidate
ROLLBACK_RELEASE=release-a
SNAPSHOT_SHA256=${digest}
ENV
  chmod 600 "$metadata"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "rollback accepted cross-release snapshot metadata"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "cross-release snapshot rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "cross-release snapshot rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "cross-release snapshot failure did not enable maintenance"
}

test_snapshot_target_metadata_rejected() {
  local remote_root="$tmp_dir/snapshot-target"
  local snapshot
  local metadata
  local digest
  local before_env="$tmp_dir/snapshot-target.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  snapshot="$remote_root/state/env-snapshots/release-b.before.env"
  metadata="$remote_root/state/env-snapshots/release-b.before.meta"
  digest="$(sha256sum "$snapshot" | cut -d' ' -f1)"
  cat > "$metadata" <<ENV
SNAPSHOT_FORMAT=1
CANDIDATE_RELEASE=release-b
ROLLBACK_RELEASE=other-target
SNAPSHOT_SHA256=${digest}
ENV
  chmod 600 "$metadata"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "rollback accepted snapshot metadata bound to another target"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "wrong-target snapshot rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "wrong-target snapshot rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "wrong-target snapshot failure did not enable maintenance"
}

test_arbitrary_snapshot_path_rejected() {
  local remote_root="$tmp_dir/arbitrary-snapshot"
  local arbitrary="$tmp_dir/arbitrary.env"
  local before_env="$tmp_dir/arbitrary-snapshot.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  cp "$remote_root/state/env-snapshots/release-b.before.env" "$arbitrary"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" \
    --env-snapshot "$arbitrary"; then
    fail "rollback accepted an arbitrary environment snapshot path"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "arbitrary snapshot rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "arbitrary snapshot rollback invoked the runtime"
}

test_public_health_failure_restores_maintenance() {
  local remote_root="$tmp_dir/public-health"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  : > "$remote_root/runtime.log"
  set_runtime_failure "$remote_root" health-public release-a

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "failed public rollback health unexpectedly succeeded"
  fi
  grep -Eq '^health-public:release-a:.*:maintenance=off$' "$remote_root/runtime.log" \
    || fail "rollback did not open the public probe window"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "public health failure did not restore maintenance"
  [[ "$(cat "$remote_root/state/active-release")" == release-b ]] \
    || fail "failed rollback committed the target release state"
}

test_schema_restore_order() {
  local remote_root="$tmp_dir/schema-order"
  local schema_backup
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  schema_backup="$remote_root/backups/db-backup-release-b-fixture.sql"
  printf 'explicit schema fixture\n' > "$schema_backup"
  chmod 600 "$schema_backup"
  : > "$remote_root/runtime.log"

  run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" \
    --schema-backup "$schema_backup" || fail "schema rollback failed"
  assert_before "$remote_root/runtime.log" enable-maintenance stop-application
  assert_before "$remote_root/runtime.log" stop-application verify-application-stopped
  assert_before "$remote_root/runtime.log" verify-application-stopped restore-schema
  assert_before "$remote_root/runtime.log" restore-schema start-release
  grep -Eq '^restore-schema:release-a:.*:maintenance=on$' "$remote_root/runtime.log" \
    || fail "schema restore ran without maintenance"
}

test_schema_restore_failure_is_safe() {
  local remote_root="$tmp_dir/schema-failure"
  local schema_backup
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  schema_backup="$remote_root/backups/db-backup-release-b-failure.sql"
  printf 'explicit schema fixture\n' > "$schema_backup"
  chmod 600 "$schema_backup"
  : > "$remote_root/runtime.log"
  set_runtime_failure "$remote_root" restore-schema release-a

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" \
    --schema-backup "$schema_backup"; then
    fail "failed schema restore unexpectedly succeeded"
  fi
  assert_before "$remote_root/runtime.log" stop-application verify-application-stopped
  assert_before "$remote_root/runtime.log" verify-application-stopped restore-schema
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "schema restore failure did not retain maintenance"
  ! grep -q '^start-release:' "$remote_root/runtime.log" \
    || fail "schema restore failure restarted a release"
  [[ "$(cat "$remote_root/state/active-release")" == release-b ]] \
    || fail "schema restore failure changed active release state"
}

test_runtime_only_rollback_skips_schema_stop() {
  local remote_root="$tmp_dir/runtime-only"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  : > "$remote_root/runtime.log"
  run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" \
    || fail "runtime-only rollback failed"
  ! grep -Eq '^(stop-application|verify-application-stopped|restore-schema):' \
    "$remote_root/runtime.log" \
    || fail "runtime-only rollback stopped writers or restored schema"
}

test_schema_path_traversal_rejected() {
  local remote_root="$tmp_dir/schema-path"
  local external_backup="$remote_root/outside-backup.sql"
  local before_env="$tmp_dir/schema-path.before.env"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  cp "$remote_root/shared/.env" "$before_env"
  printf 'outside backup\n' > "$external_backup"
  chmod 600 "$external_backup"
  : > "$remote_root/runtime.log"

  if run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" \
    --schema-backup "$remote_root/backups/../outside-backup.sql"; then
    fail "rollback accepted a schema backup outside BACKUP_DIR"
  fi
  cmp -s "$before_env" "$remote_root/shared/.env" \
    || fail "invalid schema path rollback mutated the environment"
  [[ ! -s "$remote_root/runtime.log" ]] \
    || fail "invalid schema path rollback invoked the runtime"
  [[ -f "$remote_root/state/maintenance" ]] \
    || fail "invalid schema path rollback failure did not enable maintenance"
}

test_release_identifier_traversal_rejected() {
  local remote_root="$tmp_dir/release-id-path"
  prepare_active_legacy "$remote_root"
  : > "$remote_root/runtime.log"
  if DEPLOY_ROOT="$remote_root" \
    DATA_DIR="$remote_root/data" \
    BACKUP_DIR="$remote_root/backups" \
    RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$remote_root/runtime.log" \
    RUNTIME_FAIL_ONCE="$remote_root/fail-once" \
      bash "$remote_root/releases/release-b/deploy/scripts/rollback.sh" \
        --from '../release-b' --to release-a > "$remote_root/rollback.log" 2>&1; then
    fail "rollback accepted a traversal release identifier"
  fi
  [[ ! -s "$remote_root/runtime.log" ]]
}

test_api_image_repository_consistency() {
  local release_root="$tmp_dir/image-repository/release"
  local docker_log="$tmp_dir/image-repository/docker.log"
  local docker_bin="$tmp_dir/image-repository/bin"
  mkdir -p "$release_root/deploy" "$docker_bin"
  : > "$release_root/deploy/compose.yml"
  cat > "$docker_bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_LOG"
if [[ "$1 $2" == 'image inspect' && "$3" != *:latest ]]; then
  exit 1
fi
SH
  chmod +x "$docker_bin/docker"

  PATH="$docker_bin:$PATH" \
  DOCKER_LOG="$docker_log" \
  API_IMAGE_REPOSITORY=custom-design-api \
  DEPLOY_ROOT="$tmp_dir/image-repository/root" \
    bash "$script_dir/release-runtime.sh" import-legacy "$release_root" legacy-repo
  grep -Fxq 'image inspect custom-design-api:latest' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for source image"
  grep -Fxq 'image inspect custom-design-api:legacy-repo' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for target inspection"
  grep -Fxq 'image tag custom-design-api:latest custom-design-api:legacy-repo' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for image tag"
}

if selected env-after-migrate; then
  assert_environment_failure_restored env-after-migrate migrate
fi
if selected env-after-redis; then
  assert_environment_failure_restored env-after-redis redis
fi
if selected env-after-mail; then
  assert_environment_failure_restored env-after-mail mail
fi
if selected initial-runtime-failure; then
  test_initial_runtime_failure_restores_environment
fi
if selected pending-state; then
  test_pending_state_and_snapshot_binding
fi
if selected stale-pending; then
  test_stale_pending_deployment_rejected
fi
if selected automatic-rollback; then
  test_automatic_rollback_state_identity
fi
if selected automatic-rollback-failure; then
  test_automatic_rollback_failure_is_safe
fi
if selected manual-state-mismatch; then
  test_manual_state_mismatch_rejected
fi
if selected manual-previous-mismatch; then
  test_manual_previous_mismatch_rejected
fi
if selected automatic-state-mismatch; then
  test_automatic_state_mismatch_rejected
fi
if selected automatic-active-mismatch; then
  test_automatic_active_mismatch_rejected
fi
if selected snapshot-tamper; then
  test_snapshot_tamper_rejected
fi
if selected cross-release; then
  test_cross_release_metadata_rejected
fi
if selected snapshot-target; then
  test_snapshot_target_metadata_rejected
fi
if selected arbitrary-snapshot; then
  test_arbitrary_snapshot_path_rejected
fi
if selected rollback-public-health; then
  test_public_health_failure_restores_maintenance
fi
if selected schema-order; then
  test_schema_restore_order
fi
if selected schema-failure; then
  test_schema_restore_failure_is_safe
fi
if selected runtime-only; then
  test_runtime_only_rollback_skips_schema_stop
fi
if selected schema-path; then
  test_schema_path_traversal_rejected
fi
if selected release-id-path; then
  test_release_identifier_traversal_rejected
fi
if selected api-image-repository; then
  test_api_image_repository_consistency
fi

echo "release safety ${test_case}: OK"
