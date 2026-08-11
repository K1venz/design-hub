#!/usr/bin/env bash
set -euo pipefail
umask 077

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_source="${DEPLOY_SOURCE_UNDER_TEST:-$(cd "$script_dir/.." && pwd)}"
test_case="${TEST_CASE:-all}"
case "$test_case" in
  all|env-after-migrate|env-after-redis|env-after-mail|previous-env-failures|initial-runtime-failure|pending-state|stale-pending|automatic-rollback|automatic-rollback-failure|manual-state-mismatch|manual-previous-mismatch|automatic-state-mismatch|automatic-active-mismatch|snapshot-tamper|cross-release|snapshot-target|arbitrary-snapshot|rollback-public-health|schema-order|schema-failure|runtime-only|schema-path|release-id-path|api-image-repository|selection-state|invalid-identity-guard|public-hang|docker-inspect-errors|schema-protected-copy|schema-protected-tamper|lock-recovery|env-source-swap|env-destination-tamper|selection-write-failure|lock-ownership|snapshot-create-race|schema-final-consumer|hard-timeout|deploy-retry|partial-lock-recovery|pending-recovery|legacy-split-reject|pending-invariant|partial-lock-types|initial-pending-abort|systemd-containment|final-commit-retry|dangling-state-reject|image-resume-identity|lock-tombstone|runtime-contract) ;;
  *) echo "ERROR: unknown TEST_CASE: $test_case" >&2; exit 2 ;;
esac
tmp_dir="$(mktemp -d)"
trap '[[ "${KEEP_TEST_TMP:-false}" == true ]] || rm -rf "$tmp_dir"' EXIT

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

cat > "$fake_bin/systemd-run" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
runtime_max_seconds=""
while [[ "$1" != -- ]]; do
  case "$1" in
    --property=RuntimeMaxSec=*s)
      runtime_max_seconds="${1#--property=RuntimeMaxSec=}"
      runtime_max_seconds="${runtime_max_seconds%s}"
      ;;
  esac
  shift
done
shift
if [[ -n "$runtime_max_seconds" ]]; then
  exec timeout --signal=TERM --kill-after=2s "$runtime_max_seconds" "$@"
fi
exec "$@"
SH
chmod +x "$fake_bin/systemd-run"
export PATH="$fake_bin:$PATH"
export RELEASE_ALLOW_FAKE_SYSTEMD=1

cat > "$fake_runtime" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
action="${1:?runtime action is required}"
release_dir="${2:?release directory is required}"
release_id="${3:?release identifier is required}"
argument="${4:-}"
expected_dir="$DEPLOY_ROOT/releases/$release_id"
[[ "$release_dir" == "$expected_dir" ]] || { echo "invalid runtime release directory" >&2; exit 3; }
grep -Fxq "RELEASE_ID=$release_id" "$release_dir/release.env" || { echo "invalid runtime release identity" >&2; exit 3; }
active="none"
pending="none"
maintenance="off"
if [[ -f "$DEPLOY_ROOT/state/release-selection" ]]; then
  active="$(sed -n 's/^ACTIVE_RELEASE=//p' "$DEPLOY_ROOT/state/release-selection")"
  pending="$(sed -n 's/^PENDING_RELEASE=//p' "$DEPLOY_ROOT/state/release-selection")"
fi
[[ -f "$DEPLOY_ROOT/state/maintenance" ]] && maintenance="on"
printf '%s:%s:active=%s:pending=%s:maintenance=%s\n' \
  "$action" "$release_id" "$active" "$pending" "$maintenance" >> "$RUNTIME_LOG"

if [[ "${RUNTIME_HANG_ON:-}" == "${action}:${release_id}" ]]; then
  sleep "${RUNTIME_HANG_SECONDS:-5}"
fi
if [[ "${RUNTIME_IGNORE_TERM_ON:-}" == "${action}:${release_id}" ]]; then
  trap '' TERM
  (trap '' TERM; while :; do sleep 1; done) &
  child=$!
  printf '%s\n' "$child" > "$RUNTIME_CHILD_PID_FILE"
  wait "$child"
fi
if [[ "$action" == stop-application && -n "${SCHEMA_MUTATE_SOURCE:-}" ]]; then
  printf 'mutated after stop\n' > "$SCHEMA_MUTATE_SOURCE"
  chmod 600 "$SCHEMA_MUTATE_SOURCE"
fi
if [[ "$action" == stop-application && "${SCHEMA_TAMPER_PROTECTED:-false}" == true ]]; then
  protected="$(find "$DEPLOY_ROOT/state/schema-restore-inputs" -type f -print -quit 2>/dev/null || true)"
  [[ -n "$protected" ]] && { chmod 600 "$protected"; printf 'tampered protected copy\n' > "$protected"; chmod 400 "$protected"; }
fi

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
    if [[ "${SCHEMA_MUTATE_PROTECTED_AT_RESTORE:-false}" == true ]]; then
      [[ -n "${SCHEMA_MUTATION_TARGET:-}" ]] || { echo 'missing schema mutation target' >&2; exit 2; }
      printf 'attacker replacement at final consumer\n' > "$SCHEMA_MUTATION_TARGET"
      chmod 600 "$SCHEMA_MUTATION_TARGET"
      : > "${SCHEMA_MUTATION_PROOF:?schema mutation proof is required}"
    fi
    schema_payload="$(mktemp)"
    cat > "$schema_payload"
    [[ -s "$schema_payload" ]]
    printf 'stdin:%s\n' "$(sha256sum "$schema_payload" | cut -d' ' -f1)" >> "${SCHEMA_RESTORE_LOG:-$DEPLOY_ROOT/schema-restore.log}"
    rm -f "$schema_payload"
    ;;
  prepare|build-release|enable-maintenance|migrate|start-release|health-candidate|switch-web|health-live|health-public|stop-application|verify-application-stopped|verify-application-owned)
    ;;
  *)
    echo "unexpected runtime action: $action" >&2
    exit 2
    ;;
esac
SH
chmod +x "$fake_runtime"

selected() {
  if [[ "$test_case" == all ]]; then
    printf 'release safety case: %s %s\n' "$1" "$(date +%s)"
    return 0
  fi
  [[ "$test_case" == "$1" ]]
}

read_active() {
  local root="$1"
  if [[ -f "$root/state/release-selection" ]]; then
    sed -n 's/^ACTIVE_RELEASE=//p' "$root/state/release-selection"
  else
    cat "$root/state/active-release"
  fi
}

read_previous() { sed -n 's/^PREVIOUS_RELEASE=//p' "$1/state/release-selection"; }
read_pending() { sed -n 's/^PENDING_RELEASE=//p' "$1/state/release-selection"; }
write_selection() {
  local root="$1" active="$2" previous="$3" pending="$4"
  printf '%s\n' 'SELECTION_FORMAT=1' "ACTIVE_RELEASE=$active" "PREVIOUS_RELEASE=$previous" "PENDING_RELEASE=$pending" > "$root/state/release-selection"
  chmod 600 "$root/state/release-selection"
}
write_test_manifest() {
  local destination="$1" release_id="$2" source_commit="$3"
  printf '%s\n' "RELEASE_ID=$release_id" "SOURCE_COMMIT=$source_commit" \
    'WEB_INDEX_SHA256=test-fixture' > "$destination"
}
create_borrowed_lock() {
  local root="$1" token="0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef"
  mkdir "$root/state/deploy.lock"
  printf '%s\n' 'LOCK_FORMAT=1' "TOKEN=$token" "PID=$$" "START_TICKS=$(awk '{print $22}' /proc/$$/stat)" 'OPERATION=deploy' > "$root/state/deploy.lock/owner"
  chmod 600 "$root/state/deploy.lock/owner"
  printf '%s' "$token"
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
  cat > "$remote_root/state/release-selection" <<'STATE'
SELECTION_FORMAT=1
ACTIVE_RELEASE=release-a
PREVIOUS_RELEASE=
PENDING_RELEASE=
STATE
  chmod 600 "$remote_root/state/release-selection"
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
  SCHEMA_RESTORE_LOG="$remote_root/schema-restore.log" \
  RELEASE_LOCK_TOKEN="${RELEASE_LOCK_TOKEN:-}" \
    bash "$remote_root/releases/$from_release/deploy/scripts/rollback.sh" \
      --from "$from_release" --to "$to_release" "$@" > "$log_file" 2>&1
}

deploy_from_legacy() {
  local remote_root="$1"
  local candidate="${2:-release-b}"
  run_deploy "$remote_root" "$candidate" "$remote_root/deploy.log" \
    || fail "fixture deployment ${candidate} failed"
  [[ "$(read_active "$remote_root")" == "$candidate" ]] \
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
  [[ -z "$(read_pending "$remote_root")" ]] \
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
  [[ "$(read_pending "$remote_root")" == release-initial ]] \
    || fail "unrecoverable initial runtime failure lost pending state"
  [[ -z "$(read_active "$remote_root")" ]] \
    || fail "failed initial release was recorded active"
  ! grep -Fq "$sentinel" "$remote_root/deploy.log" \
    || fail "initial runtime failure leaked an environment secret"
}

test_previous_release_environment_failures_restore_bytes() {
  local variant remote_root original
  for variant in migrate redis mail; do
    remote_root="$tmp_dir/previous-env-$variant"
    prepare_active_legacy "$remote_root"
    case "$variant" in
      migrate)
        sed -i '/^EMAIL_VERIFICATION_CODE_PEPPER=/d;/^REDIS_PASSWORD=/cREDIS_PASSWORD=invalid' "$remote_root/shared/.env"
        printf 'PASSWORD_RESET_CODE_PEPPER=%s\n' 'abcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789' >> "$remote_root/shared/.env"
        ;;
      redis) sed -i 's/^REDIS_URL=.*/REDIS_URL=redis:\/\/wrong@redis:6379\/0/' "$remote_root/shared/.env" ;;
      mail) sed -i '/^SMTP_FROM=/d' "$remote_root/shared/.env"; set_runtime_failure "$remote_root" prepare release-b ;;
    esac
    original="$remote_root/original.env"; cp "$remote_root/shared/.env" "$original"
    if run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then fail "previous release $variant failure unexpectedly succeeded"; fi
    cmp -s "$original" "$remote_root/shared/.env" || fail "previous release $variant failure changed environment bytes"
    assert_file_mode_600 "$remote_root/shared/.env"
    [[ "$(read_active "$remote_root")" == release-a && -z "$(read_pending "$remote_root")" ]] || fail "previous release $variant failure changed selection"
    [[ ! -e "$remote_root/state/maintenance" ]] || fail "pre-runtime $variant failure left maintenance"
  done
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
  [[ "$(read_active "$remote_root")" == release-b ]]
  [[ "$(read_previous "$remote_root")" == release-a ]]
  [[ -z "$(read_pending "$remote_root")" ]] \
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
  write_selection "$remote_root" release-a '' other-candidate

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
  [[ "$(read_active "$remote_root")" == release-a ]]
  [[ -z "$(read_pending "$remote_root")" ]]
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
  [[ "$(read_active "$remote_root")" == release-a ]] \
    || fail "failed automatic rollback changed active release state"
  [[ "$(read_pending "$remote_root")" == release-b ]] \
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
  write_selection "$remote_root" release-a release-a ''
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
  write_selection "$remote_root" release-b other-target ''
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
  write_selection "$remote_root" release-a '' other-candidate
  token="$(create_borrowed_lock "$remote_root")"
  : > "$remote_root/runtime.log"

  if RELEASE_LOCK_TOKEN="$token" run_rollback \
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
  write_selection "$remote_root" other-active '' release-b
  token="$(create_borrowed_lock "$remote_root")"
  : > "$remote_root/runtime.log"

  if RELEASE_LOCK_TOKEN="$token" run_rollback \
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
  [[ "$(read_active "$remote_root")" == release-b ]] \
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
  [[ "$(read_active "$remote_root")" == release-b ]] \
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
  write_test_manifest "$release_root/release.env" legacy-repo legacy-import
  cat > "$docker_bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$*" >> "$DOCKER_LOG"
if [[ "$1 $2" == 'image inspect' ]]; then
  [[ "$*" != *--format* ]] || { printf 'sha256:%064d\n' 0; exit 0; }
  [[ "$3" == *:latest || -f "$LEGACY_TAGGED" ]]
  exit
fi
if [[ "$1 $2" == 'image tag' ]]; then : > "$LEGACY_TAGGED"; exit 0; fi
SH
  chmod +x "$docker_bin/docker"

  PATH="$docker_bin:$PATH" \
  DOCKER_LOG="$docker_log" \
  LEGACY_TAGGED="$tmp_dir/image-repository/tagged" \
  API_IMAGE_REPOSITORY=custom-design-api \
  DEPLOY_ROOT="$tmp_dir/image-repository/root" \
    bash "$script_dir/release-runtime.sh" import-legacy "$release_root" legacy-repo
  grep -Fq 'custom-design-api:latest' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for source image"
  grep -Fxq 'image inspect custom-design-api:legacy-repo' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for target inspection"
  grep -Fxq 'image tag custom-design-api:latest custom-design-api:legacy-repo' "$docker_log" \
    || fail "legacy import ignored API_IMAGE_REPOSITORY for image tag"
  assert_file_mode_600 "$tmp_dir/image-repository/root/state/image-identities/legacy-repo.api"
}

test_single_selection_state() {
  local remote_root="$tmp_dir/selection-state"
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  [[ -f "$remote_root/state/release-selection" ]] || fail "single release-selection state was not created"
  grep -Fxq 'ACTIVE_RELEASE=release-b' "$remote_root/state/release-selection"
  grep -Fxq 'PREVIOUS_RELEASE=release-a' "$remote_root/state/release-selection"
  grep -Fxq 'PENDING_RELEASE=' "$remote_root/state/release-selection"
  for legacy in active-release previous-release pending-release; do
    [[ ! -e "$remote_root/state/$legacy" ]] || fail "legacy split state remains: $legacy"
  done
}

test_invalid_identity_arms_guard() {
  local remote_root="$tmp_dir/invalid-guard"
  prepare_active_legacy "$remote_root"
  if DEPLOY_ROOT="$remote_root" DATA_DIR="$remote_root/data" BACKUP_DIR="$remote_root/backups" \
    RELEASE_RUNTIME="$fake_runtime" RUNTIME_LOG="$remote_root/runtime.log" RUNTIME_FAIL_ONCE="$remote_root/fail-once" \
    bash "$remote_root/releases/release-b/deploy/scripts/rollback.sh" --from '../release-b' --to release-a \
      > "$remote_root/rollback.log" 2>&1; then
    fail "invalid rollback identity was accepted"
  fi
  [[ -f "$remote_root/state/maintenance" ]] || fail "invalid identity failed before maintenance guard"
  [[ ! -d "$remote_root/state/deploy.lock" ]] || fail "invalid identity leaked the release lock"
  rm -f "$remote_root/state/maintenance"
  if run_rollback "$remote_root" release-b release-b "$remote_root/same-release.log"; then
    fail "rollback accepted identical source and target"
  fi
  [[ -f "$remote_root/state/maintenance" ]] || fail "identical release failure bypassed maintenance guard"
}

test_public_probe_hang_is_bounded() {
  local remote_root="$tmp_dir/public-hang" rollback_root="$tmp_dir/rollback-public-hang"
  local started elapsed hang_seconds=30 elapsed_limit=20
  case "$(uname -s)" in MINGW*|MSYS*) hang_seconds=2; elapsed_limit=30 ;; esac
  prepare_active_legacy "$remote_root"
  started="$(date +%s)"
  if RUNTIME_HANG_ON=health-public:release-b RUNTIME_HANG_SECONDS="$hang_seconds" \
    PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS=1 PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS=1 \
    run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then
    fail "hanging public probe unexpectedly succeeded"
  fi
  elapsed="$(( $(date +%s) - started ))"
  [[ "$elapsed" -le "$elapsed_limit" ]] || fail "public probe was not bounded (${elapsed}s)"
  [[ ! -d "$remote_root/state/deploy.lock" ]] || fail "public hang leaked the release lock"

  prepare_active_legacy "$rollback_root"; deploy_from_legacy "$rollback_root"
  started="$(date +%s)"
  if RUNTIME_HANG_ON=health-public:release-a RUNTIME_HANG_SECONDS="$hang_seconds" \
    PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS=1 PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS=1 \
    run_rollback "$rollback_root" release-b release-a "$rollback_root/rollback.log"; then
    fail "hanging rollback public probe unexpectedly succeeded"
  fi
  elapsed="$(( $(date +%s) - started ))"
  [[ "$elapsed" -le "$elapsed_limit" ]] || fail "rollback public probe was not bounded (${elapsed}s)"
  [[ -f "$rollback_root/state/maintenance" && "$(read_active "$rollback_root")" == release-b ]] \
    || fail "rollback public hang lost maintenance or committed selection"
  [[ ! -d "$rollback_root/state/deploy.lock" ]] || fail "rollback public hang leaked the release lock"
}

test_docker_inspect_errors_fail_fast() {
  local root="$tmp_dir/docker-inspect" bin="$tmp_dir/docker-inspect/bin"
  mkdir -p "$root/deploy" "$bin"
  : > "$root/deploy/compose.yml"
  write_test_manifest "$root/release.env" release-x test-fixture
  cat > "$bin/docker" <<'SH'
#!/usr/bin/env bash
case "${DOCKER_FAKE_MODE:-daemon}" in
  daemon) echo 'Cannot connect to the Docker daemon' >&2; exit 1 ;;
  missing) echo "Error: No such container: ${*: -1}" >&2; exit 1 ;;
  stopped)
    [[ "$1 $2" == 'container inspect' ]] && exit 0
    printf 'false\n'
    ;;
  running)
    [[ "$1 $2" == 'container inspect' ]] && exit 0
    printf 'true\n'
    ;;
  owned) printf '%s\n' "${OWNED_RELEASE:-release-x}" ;;
  foreign) printf 'another-release\n' ;;
esac
SH
  chmod +x "$bin/docker"
  if PATH="$bin:$PATH" DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-stopped "$root" release-x; then
    fail "Docker daemon inspect error was treated as a missing container"
  fi
  PATH="$bin:$PATH" DOCKER_FAKE_MODE=missing DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-stopped "$root" release-x \
    || fail "explicit Docker missing-container result was rejected"
  PATH="$bin:$PATH" DOCKER_FAKE_MODE=stopped DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-stopped "$root" release-x \
    || fail "explicit stopped containers were rejected"
  if PATH="$bin:$PATH" DOCKER_FAKE_MODE=running DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-stopped "$root" release-x; then
    fail "running container was accepted before schema restore"
  fi
  PATH="$bin:$PATH" DOCKER_FAKE_MODE=owned OWNED_RELEASE=release-x DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-owned "$root" release-x \
    || fail "candidate-owned containers were rejected"
  PATH="$bin:$PATH" DOCKER_FAKE_MODE=missing DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-owned "$root" release-x \
    || fail "explicit missing containers were rejected during ownership check"
  if PATH="$bin:$PATH" DOCKER_FAKE_MODE=foreign DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-owned "$root" release-x; then
    fail "containers from another release were accepted"
  fi
  if PATH="$bin:$PATH" DOCKER_FAKE_MODE=daemon DEPLOY_ROOT="$tmp_dir/docker-inspect/deploy-root" \
    bash "$script_dir/release-runtime.sh" verify-application-owned "$root" release-x; then
    fail "Docker daemon error was treated as missing during ownership check"
  fi
}

test_schema_uses_protected_copy() {
  local remote_root="$tmp_dir/schema-copy" source original_digest restore_path restore_digest
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  source="$remote_root/backups/explicit.sql"
  printf 'original immutable schema\n' > "$source"
  chmod 600 "$source"
  original_digest="$(sha256sum "$source" | cut -d' ' -f1)"
  : > "$remote_root/runtime.log"
  SCHEMA_MUTATE_SOURCE="$source" run_rollback "$remote_root" release-b release-a \
    "$remote_root/rollback.log" --schema-backup "$source" || fail "protected schema rollback failed"
  IFS=: read -r restore_path restore_digest < "$remote_root/schema-restore.log"
  [[ "$restore_path" != "$source" ]] || fail "runtime restored mutable caller schema path"
  [[ "$restore_digest" == "$original_digest" ]] || fail "protected schema copy changed after stop"
}

test_explicit_stale_lock_recovery() {
  local remote_root="$tmp_dir/lock-recovery" recovery
  mkdir -p "$remote_root/state/deploy.lock"
  cat > "$remote_root/state/deploy.lock/owner" <<'EOF'
LOCK_FORMAT=1
TOKEN=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef
PID=99999999
START_TICKS=1
OPERATION=deploy
EOF
  chmod 600 "$remote_root/state/deploy.lock/owner"
  recovery="$script_dir/recover-release-lock.sh"
  [[ -x "$recovery" ]] || fail "stale lock recovery entry point is missing"
  DEPLOY_ROOT="$remote_root" bash "$recovery" --confirm-stale-lock-recovery
  [[ ! -d "$remote_root/state/deploy.lock" ]] || fail "stale lock recovery left the lock"
}

test_environment_source_swap_never_reaches_live() {
  local remote_root="$tmp_dir/env-source-swap" wrapper="$tmp_dir/env-source-swap/bin" before
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  before="$remote_root/before.env"
  cp "$remote_root/shared/.env" "$before"
  mkdir -p "$wrapper"
  cat > "$wrapper/cp" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
for candidate in "$@"; do
  if [[ "$candidate" == *env-snapshots/release-b.before.env && ! -e "$SWAP_DONE" ]]; then
    printf 'attacker bytes\n' > "$candidate"
    chmod 600 "$candidate"
    : > "$SWAP_DONE"
  fi
done
exec "$REAL_CP" "$@"
SH
  chmod +x "$wrapper/cp"
  if PATH="$wrapper:$PATH" REAL_CP=/usr/bin/cp SWAP_DONE="$remote_root/swap.done" \
    run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "rollback accepted a snapshot swapped during protected copy"
  fi
  cmp -s "$before" "$remote_root/shared/.env" || fail "source swap wrote unverified bytes to live environment"
  [[ -f "$remote_root/state/maintenance" ]] || fail "source swap did not retain maintenance"
}

test_selection_write_failure_is_atomic_and_retryable() {
  local remote_root="$tmp_dir/selection-write" wrapper="$tmp_dir/selection-write/bin" before
  prepare_active_legacy "$remote_root"
  deploy_from_legacy "$remote_root"
  before="$remote_root/selection.before"
  cp "$remote_root/state/release-selection" "$before"
  mkdir -p "$wrapper"
  cat > "$wrapper/mv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
destination="${*: -1}"
if [[ "$destination" == */state/release-selection && ! -e "$MV_FAILED" ]]; then
  : > "$MV_FAILED"
  exit 71
fi
exec /usr/bin/mv "$@"
SH
  chmod +x "$wrapper/mv"
  if PATH="$wrapper:$PATH" MV_FAILED="$remote_root/mv.failed" \
    run_rollback "$remote_root" release-b release-a "$remote_root/rollback-fail.log"; then
    fail "selection write failure unexpectedly succeeded"
  fi
  cmp -s "$before" "$remote_root/state/release-selection" || fail "selection write failure produced split state"
  [[ -f "$remote_root/state/maintenance" ]] || fail "selection failure did not retain maintenance"
  run_rollback "$remote_root" release-b release-a "$remote_root/rollback-retry.log" || fail "selection retry failed"
  [[ "$(read_active "$remote_root")" == release-a && -z "$(read_previous "$remote_root")" ]] || fail "selection retry did not commit atomically"
}

test_lock_ownership_boundaries() {
  local root="$tmp_dir/lock-ownership" token wrong
  mkdir -p "$root/state"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  acquire_release_lock "$root/state/deploy.lock" deploy
  token="$release_lock_token"
  wrong="ffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffffff"
  if borrow_release_lock "$root/state/deploy.lock" "$wrong"; then fail "wrong lock token borrowed a live lock"; fi
  borrow_release_lock "$root/state/deploy.lock" "$token" || fail "owner token could not borrow its live lock"
  if DEPLOY_ROOT="$root" bash "$script_dir/recover-release-lock.sh" --confirm-stale-lock-recovery >/dev/null 2>&1; then
    fail "stale recovery removed a live owner lock"
  fi
  : > "$root/state/deploy.lock/obstruction"
  if release_release_lock "$root/state/deploy.lock" "$token"; then fail "lock cleanup failure was silently accepted"; fi
}

test_environment_destination_tamper_restores_rescue() {
  local remote_root="$tmp_dir/env-destination-tamper" wrapper="$tmp_dir/env-destination-tamper/bin" before
  prepare_active_legacy "$remote_root"; deploy_from_legacy "$remote_root"
  before="$remote_root/before.env"; cp "$remote_root/shared/.env" "$before"; mkdir -p "$wrapper"
  cat > "$wrapper/mv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
destination="${*: -1}"
/usr/bin/mv "$@"
if [[ "$destination" == */shared/.env && ! -e "$TAMPER_DONE" ]]; then
  printf 'post-rename attacker bytes\n' > "$destination"; chmod 600 "$destination"; : > "$TAMPER_DONE"
fi
SH
  chmod +x "$wrapper/mv"
  if PATH="$wrapper:$PATH" TAMPER_DONE="$remote_root/tamper.done" run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log"; then
    fail "post-rename environment tamper unexpectedly succeeded"
  fi
  cmp -s "$before" "$remote_root/shared/.env" || fail "post-verify failure left a bad live environment"
  [[ -f "$remote_root/state/maintenance" ]] || fail "destination tamper did not retain maintenance"
}

test_protected_schema_tamper_is_rejected() {
  local remote_root="$tmp_dir/schema-protected-tamper" source
  prepare_active_legacy "$remote_root"; deploy_from_legacy "$remote_root"
  source="$remote_root/backups/explicit.sql"; printf 'schema bytes\n' > "$source"; chmod 600 "$source"; : > "$remote_root/runtime.log"
  if SCHEMA_TAMPER_PROTECTED=true run_rollback "$remote_root" release-b release-a "$remote_root/rollback.log" --schema-backup "$source"; then
    fail "tampered protected schema input unexpectedly restored"
  fi
  ! grep -q '^restore-schema:' "$remote_root/runtime.log" || fail "tampered protected schema reached database import"
  ! grep -q '^start-release:' "$remote_root/runtime.log" || fail "tampered schema failure restarted a release"
  [[ "$(read_active "$remote_root")" == release-b && -f "$remote_root/state/maintenance" ]] || fail "schema tamper lost safe state"
}

test_snapshot_creation_rejects_changing_source() {
  local root="$tmp_dir/snapshot-create-race" bin="$tmp_dir/snapshot-create-race/bin"
  mkdir -p "$root/snapshots" "$bin"
  write_valid_environment "$root/live.env" stable-source
  cat > "$bin/cat" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf 'changed during copy\n' > "$LIVE_SOURCE"; chmod 600 "$LIVE_SOURCE"
exec /usr/bin/cat "$@"
SH
  chmod +x "$bin/cat"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  if PATH="$bin:$PATH" LIVE_SOURCE="$root/live.env" create_bound_environment_snapshot "$root/live.env" \
    "$root/snapshots/race.before.env" "$root/snapshots/race.before.meta" race rollback; then
    fail "changing live environment was self-signed as a valid snapshot"
  fi
  [[ ! -e "$root/snapshots/race.before.env" && ! -e "$root/snapshots/race.before.meta" ]] \
    || fail "failed snapshot creation left acceptable canonical files"
}

test_schema_final_consumer_is_fixed() {
  local remote_root="$tmp_dir/schema-final-consumer" source expected
  prepare_active_legacy "$remote_root"; deploy_from_legacy "$remote_root"
  source="$remote_root/backups/final.sql"; printf 'fixed schema input\n' > "$source"; chmod 600 "$source"
  expected="$(sha256sum "$source" | cut -d' ' -f1)"; : > "$remote_root/runtime.log"
  SCHEMA_MUTATE_PROTECTED_AT_RESTORE=true SCHEMA_MUTATION_TARGET="$source" \
    SCHEMA_MUTATION_PROOF="$remote_root/mutation.proof" run_rollback "$remote_root" release-b release-a \
    "$remote_root/rollback.log" --schema-backup "$source" || fail "fixed schema consumer rollback failed"
  [[ -f "$remote_root/mutation.proof" ]] || fail "schema final-consumer fixture did not execute its mutation"
  grep -Fxq 'attacker replacement at final consumer' "$source" || fail "schema mutation target was not changed"
  grep -Fq ":$expected" "$remote_root/schema-restore.log" || fail "restore reopened bytes after final digest verification"
}

test_timeout_kills_term_ignoring_tree() {
  local remote_root="$tmp_dir/hard-timeout"
  prepare_active_legacy "$remote_root"
  grep -Fq -- "'--property=KillMode=control-group'" "$script_dir/release-state.sh" || fail "Linux timeout does not contain the complete cgroup"
  grep -Fq -- "'--property=TimeoutStopSec=2s'" "$script_dir/release-state.sh" || fail "Linux timeout lacks bounded cgroup kill escalation"
  if timeout 25 env RUNTIME_IGNORE_TERM_ON=health-public:release-b RUNTIME_CHILD_PID_FILE="$remote_root/child.pid" \
    PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS=1 PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS=1 \
    DEPLOY_ROOT="$remote_root" DATA_DIR="$remote_root/data" BACKUP_DIR="$remote_root/backups" \
    RELEASE_RUNTIME="$fake_runtime" RUNTIME_LOG="$remote_root/runtime.log" RUNTIME_FAIL_ONCE="$remote_root/fail-once" \
    bash "$remote_root/releases/release-b/deploy/scripts/deploy.sh" release-b > "$remote_root/deploy.log" 2>&1; then
    fail "TERM-ignoring public probe unexpectedly succeeded"
  fi
  [[ -s "$remote_root/child.pid" ]] || fail "TERM-ignoring descendant fixture did not start"
  child_pid="$(cat "$remote_root/child.pid")"
  if kill -0 "$child_pid" 2>/dev/null; then
    if [[ "$(awk '{print $3}' "/proc/$child_pid/stat" 2>/dev/null || true)" != Z ]]; then
      case "$(uname -s)" in
        MINGW*|MSYS*) kill -KILL "$child_pid" 2>/dev/null || true ;;
        *) fail "controller timeout left a descendant process alive" ;;
      esac
    fi
  fi
}

test_deploy_snapshot_initialization_is_retryable() {
  local remote_root="$tmp_dir/deploy-retry" wrapper="$tmp_dir/deploy-retry/bin"
  prepare_active_legacy "$remote_root"; mkdir -p "$wrapper"
  cat > "$wrapper/mv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
destination="${*: -1}"
if [[ "$destination" == */state/release-selection && ! -e "$MV_FAILED" ]]; then : > "$MV_FAILED"; exit 72; fi
exec /usr/bin/mv "$@"
SH
  chmod +x "$wrapper/mv"
  if PATH="$wrapper:$PATH" MV_FAILED="$remote_root/mv.failed" run_deploy "$remote_root" release-b "$remote_root/first.log"; then
    fail "pending selection write failure unexpectedly succeeded"
  fi
  run_deploy "$remote_root" release-b "$remote_root/retry.log" || fail "same release could not retry after snapshot/pending interruption"
  [[ "$(read_active "$remote_root")" == release-b ]] || fail "retry did not activate candidate"
}

test_partial_lock_is_explicitly_recoverable() {
  local root="$tmp_dir/partial-lock"
  mkdir -p "$root/state/deploy.lock"; chmod 700 "$root/state/deploy.lock"
  printf '%s\n' 'LOCK_FORMAT=1' \
    'TOKEN=0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef' \
    'PID=99999999' 'START_TICKS=1' 'OPERATION=deploy' \
    > "$root/state/deploy.lock/.owner.partial"
  chmod 600 "$root/state/deploy.lock/.owner.partial"
  DEPLOY_ROOT="$root" bash "$script_dir/recover-release-lock.sh" --confirm-stale-lock-recovery \
    || fail "explicit recovery could not clear a partial acquisition lock"
  [[ ! -d "$root/state/deploy.lock" ]] || fail "partial lock recovery left the lock"
}

test_partial_lock_types_fail_closed() {
  local root="$tmp_dir/partial-lock-types" token
  mkdir -p "$root/state"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  acquire_release_lock "$root/state/deploy.lock" deploy
  token="$release_lock_token"
  mkdir "$root/state/deploy.lock/.owner.directory"
  if release_release_lock "$root/state/deploy.lock" "$token"; then
    fail "lock cleanup accepted an owner-shaped directory"
  fi
  [[ -f "$root/state/deploy.lock/owner" ]] || fail "failed cleanup deleted owner evidence"
  if DEPLOY_ROOT="$root" bash "$script_dir/recover-release-lock.sh" --confirm-stale-lock-recovery; then
    fail "lock recovery accepted an owner-shaped directory"
  fi
  [[ -f "$root/state/deploy.lock/owner" ]] || fail "failed recovery deleted owner evidence"
  rmdir "$root/state/deploy.lock/.owner.directory"
  mkfifo "$root/state/deploy.lock/.owner.fifo"
  if release_release_lock "$root/state/deploy.lock" "$token"; then
    fail "lock cleanup accepted an owner-shaped FIFO"
  fi
  [[ -f "$root/state/deploy.lock/owner" ]] || fail "FIFO cleanup deleted owner evidence"
  rm "$root/state/deploy.lock/.owner.fifo"
  release_release_lock "$root/state/deploy.lock" "$token" || fail "valid lock cleanup failed"
}

test_lock_cleanup_uses_atomic_tombstone() {
  local root="$tmp_dir/lock-tombstone" bin="$tmp_dir/lock-tombstone/bin" token
  mkdir -p "$root/state" "$bin"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  acquire_release_lock "$root/state/deploy.lock" deploy
  token="$release_lock_token"
  cat > "$bin/rmdir" <<'SH'
#!/usr/bin/env bash
case "$1" in *.released.*) exit 75 ;; esac
exec /usr/bin/rmdir "$@"
SH
  chmod +x "$bin/rmdir"
  if PATH="$bin:$PATH" release_release_lock "$root/state/deploy.lock" "$token"; then
    fail "injected tombstone removal failure unexpectedly succeeded"
  fi
  [[ ! -e "$root/state/deploy.lock" ]] || fail "cleanup failure left an ownerless canonical lock"
  compgen -G "$root/state/deploy.lock.released.$token" >/dev/null || fail "cleanup failure lost the protected tombstone"
  acquire_release_lock "$root/state/deploy.lock" deploy || fail "retired tombstone blocked a new canonical lock"
  release_release_lock "$root/state/deploy.lock" "$release_lock_token" || fail "new canonical lock cleanup failed"
}

test_runtime_contract_is_protected() {
  local root="$tmp_dir/runtime-contract"
  mkdir -p "$root"
  printf '#!/usr/bin/env bash\nexit 0\n' > "$root/runtime"
  chmod 755 "$root/runtime"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  require_runtime_contract "$root/runtime" || fail "protected absolute runtime was rejected"
  if require_runtime_contract relative-runtime; then fail "relative custom runtime was accepted"; fi
  case "$(uname -s)" in
    MINGW*|MSYS*) grep -Fq '! -L "$runtime"' "$script_dir/release-state.sh" || fail "runtime symlink rejection is missing" ;;
    *)
      ln -s "$root/runtime" "$root/runtime-link"
      if require_runtime_contract "$root/runtime-link"; then fail "symlink custom runtime was accepted"; fi
      ;;
  esac
  case "$(uname -s)" in
    MINGW*|MSYS*) grep -Fq '8#$mode & 8#022' "$script_dir/release-state.sh" || fail "writable runtime rejection is missing" ;;
    *)
      chmod 777 "$root/runtime"
      if require_runtime_contract "$root/runtime"; then fail "writable custom runtime was accepted"; fi
      ;;
  esac
}

test_initial_pending_abort_is_explicit_and_safe() {
  local root="$tmp_dir/initial-pending-abort" recovery original
  mkdir -p "$root/shared" "$root/state" "$root/backups"
  stage_release "$root" release-initial
  write_valid_environment "$root/shared/.env" initial-abort-secret
  original="$root/original.env"; cp "$root/shared/.env" "$original"
  : > "$root/runtime.log"
  set_runtime_failure "$root" health-live release-initial
  if run_deploy "$root" release-initial "$root/deploy-fail.log"; then fail "initial crash fixture succeeded"; fi
  [[ -z "$(read_active "$root")" && "$(read_pending "$root")" == release-initial ]] \
    || fail "initial crash did not retain empty-active pending state"
  recovery="$root/releases/release-initial/deploy/scripts/recover-pending-release.sh"
  if DEPLOY_ROOT="$root" DATA_DIR="$root/data" BACKUP_DIR="$root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$root/runtime.log" RUNTIME_FAIL_ONCE="$root/fail-once" bash "$recovery" \
      --initial-abort --candidate wrong; then
    fail "initial abort accepted wrong candidate"
  fi
  sed -i 's/^RELEASE_ID=.*/RELEASE_ID=wrong-manifest/' "$root/releases/release-initial/release.env"
  if DEPLOY_ROOT="$root" DATA_DIR="$root/data" BACKUP_DIR="$root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$root/runtime.log" RUNTIME_FAIL_ONCE="$root/fail-once" bash "$recovery" \
      --initial-abort --candidate release-initial; then
    fail "initial abort accepted a mismatched candidate manifest"
  fi
  sed -i 's/^RELEASE_ID=.*/RELEASE_ID=release-initial/' "$root/releases/release-initial/release.env"
  set_runtime_failure "$root" verify-application-owned release-initial
  if DEPLOY_ROOT="$root" DATA_DIR="$root/data" BACKUP_DIR="$root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$root/runtime.log" RUNTIME_FAIL_ONCE="$root/fail-once" bash "$recovery" \
      --initial-abort --candidate release-initial; then
    fail "initial abort stopped an unowned candidate runtime"
  fi
  [[ "$(read_pending "$root")" == release-initial && -f "$root/state/maintenance" ]] \
    || fail "ownership rejection lost pending or maintenance state"
  DEPLOY_ROOT="$root" DATA_DIR="$root/data" BACKUP_DIR="$root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$root/runtime.log" RUNTIME_FAIL_ONCE="$root/fail-once" bash "$recovery" \
      --initial-abort --candidate release-initial || fail "initial pending abort failed"
  [[ -z "$(read_active "$root")" && -z "$(read_pending "$root")" ]] || fail "initial abort did not clear pending atomically"
  cmp -s "$original" "$root/shared/.env" || fail "initial abort did not restore bound environment"
  [[ -f "$root/state/maintenance" ]] || fail "initial abort opened traffic"
  grep -q '^stop-application:release-initial:' "$root/runtime.log" || fail "initial abort did not stop candidate"
  grep -q '^verify-application-stopped:release-initial:' "$root/runtime.log" || fail "initial abort did not verify candidate stop"
}

test_systemd_cgroup_boundary_is_required() {
  local root="$tmp_dir/systemd-containment" bin="$tmp_dir/systemd-containment/bin" args escaped_pid
  mkdir -p "$root" "$bin"
cat > "$bin/systemd-run" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
printf '%s\n' "$@" > "$SYSTEMD_ARGS_LOG"
environment=("PATH=$PATH")
while [[ "$1" != -- ]]; do
  case "$1" in --setenv=*) environment+=("${1#--setenv=}") ;; esac
  shift
done
shift
if [[ "${FAKE_SYSTEMD_TIMEOUT:-false}" != true ]]; then exec env -i "${environment[@]}" "$@"; fi
env -i "${environment[@]}" ESCAPED_PID_FILE="$ESCAPED_PID_FILE" "$@" & leader=$!
for _ in $(seq 1 50); do [[ -s "$ESCAPED_PID_FILE" ]] && break; sleep 0.02; done
[[ -s "$ESCAPED_PID_FILE" ]] || { kill -KILL "$leader" 2>/dev/null || true; exit 1; }
kill -KILL "$(cat "$ESCAPED_PID_FILE")" "$leader" 2>/dev/null || true
wait "$leader" 2>/dev/null || true
exit 124
SH
  chmod +x "$bin/systemd-run"
  cat > "$bin/uname" <<'SH'
#!/usr/bin/env bash
printf 'Linux\n'
SH
  chmod +x "$bin/uname"
  cat > "$bin/setsid" <<'SH'
#!/usr/bin/env bash
exec "$@"
SH
  chmod +x "$bin/setsid"
  cat > "$root/env-probe" <<'SH'
#!/usr/bin/env bash
env | sort > "$1"
SH
  chmod +x "$root/env-probe"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  SYSTEMD_ARGS_LOG="$root/args" PATH="$bin:$PATH" PUBLIC_HEALTH_URL=https://health.invalid/ \
    PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS=2 PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS=3 \
    DEPLOY_ROOT=/srv/design-hub DATA_DIR=/srv/data BACKUP_DIR=/srv/backups MYSQL_ENV=/srv/mysql.env \
    SERVER_IP=192.0.2.1 API_IMAGE_REPOSITORY=registry.invalid/design-hub SMTP_PASSWORD=must-not-cross \
    run_with_hard_timeout 3 "$root/env-probe" "$root/probe-env" \
    || fail "fake systemd controller boundary failed"
  args="$(cat "$root/args")"
  grep -Fxq -- '--wait' "$root/args" || fail "systemd controller does not wait for the unit result"
  grep -Fxq -- '--collect' "$root/args" || fail "systemd controller does not collect the unit"
  grep -Fxq -- '--property=KillMode=control-group' "$root/args" || fail "systemd controller lacks cgroup-wide kill"
  grep -Fxq -- '--property=RuntimeMaxSec=3s' "$root/args" || fail "systemd controller lacks hard runtime deadline"
  grep -Fxq -- '--property=TimeoutStopSec=2s' "$root/args" || fail "systemd controller lacks bounded stop"
  for expected in \
    '--setenv=PUBLIC_HEALTH_URL=https://health.invalid/' \
    '--setenv=PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS=2' \
    '--setenv=PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS=3' \
    '--setenv=DEPLOY_ROOT=/srv/design-hub' '--setenv=DATA_DIR=/srv/data' \
    '--setenv=BACKUP_DIR=/srv/backups' '--setenv=MYSQL_ENV=/srv/mysql.env' \
    '--setenv=SERVER_IP=192.0.2.1' '--setenv=API_IMAGE_REPOSITORY=registry.invalid/design-hub'; do
    grep -Fxq -- "$expected" "$root/args" || fail "systemd controller omitted allowlisted environment: $expected"
  done
  ! grep -q 'SMTP_PASSWORD' "$root/args" || fail "systemd controller forwarded a secret environment value"
  grep -Fxq 'PUBLIC_HEALTH_URL=https://health.invalid/' "$root/probe-env" || fail "clean service environment lost public health URL"
  ! grep -q 'SMTP_PASSWORD' "$root/probe-env" || fail "clean service environment received a secret"
  [[ "$args" != *setsid* ]] || fail "controller still relies on escapable process groups"
  cat > "$root/escaped-probe" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
setsid bash -c 'trap "" TERM; while :; do sleep 1; done' &
printf '%s\n' "$!" > "$ESCAPED_PID_FILE"
wait
SH
  chmod +x "$root/escaped-probe"
  if SYSTEMD_ARGS_LOG="$root/timeout-args" ESCAPED_PID_FILE="$root/escaped.pid" \
    FAKE_SYSTEMD_TIMEOUT=true PATH="$bin:$PATH" run_with_hard_timeout 1 "$root/escaped-probe"; then
    fail "timed-out transient unit unexpectedly succeeded"
  fi
  escaped_pid="$(cat "$root/escaped.pid")"
  if kill -0 "$escaped_pid" 2>/dev/null \
    && [[ "$(awk '{print $3}' "/proc/$escaped_pid/stat" 2>/dev/null || true)" != Z ]]; then
    kill -KILL "$escaped_pid" 2>/dev/null || true
    fail "escaped setsid descendant survived cgroup timeout boundary"
  fi
}

test_final_selection_commit_retry() {
  local root="$tmp_dir/final-commit-retry" wrapper="$tmp_dir/final-commit-retry/bin"
  prepare_active_legacy "$root"; mkdir -p "$wrapper"
  cat > "$wrapper/mv" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
destination="${*: -1}"
if [[ "$destination" == */state/release-selection ]]; then
  count=0; [[ ! -f "$MV_COUNT" ]] || count="$(cat "$MV_COUNT")"; count=$((count + 1)); printf '%s\n' "$count" > "$MV_COUNT"
  if [[ "$count" -eq 2 && ! -e "$MV_FAILED" ]]; then : > "$MV_FAILED"; exit 73; fi
fi
exec /usr/bin/mv "$@"
SH
  chmod +x "$wrapper/mv"
  if PATH="$wrapper:$PATH" MV_COUNT="$root/mv.count" MV_FAILED="$root/mv.failed" \
    run_deploy "$root" release-b "$root/first.log"; then fail "final selection commit failure succeeded"; fi
  run_deploy "$root" release-b "$root/retry.log" || fail "same identity retry after final commit failure failed"
  [[ "$(read_active "$root")" == release-b && -z "$(read_pending "$root")" ]] || fail "retry did not commit candidate"
}

test_dangling_release_state_is_rejected() {
  local root="$tmp_dir/dangling-state"
  mkdir -p "$root/state"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  case "$(uname -s)" in
    MINGW*|MSYS*)
      grep -Fq '! -L "$selection_file"' "$script_dir/release-state.sh" || fail "dangling selection symlink is not rejected"
      grep -Fq '|| -L "$state_dir/active-release"' "$script_dir/release-state.sh" || fail "dangling legacy symlink is not rejected"
      ;;
    *)
      ln -s "$root/missing-selection" "$root/state/release-selection"
      if load_release_state "$root/state/release-selection"; then fail "dangling selection symlink was treated as initial state"; fi
      rm "$root/state/release-selection"
      ln -s "$root/missing-active" "$root/state/active-release"
      if load_release_state "$root/state/release-selection"; then fail "dangling legacy symlink was ignored"; fi
      ;;
  esac
}

test_api_image_resume_is_manifest_bound() {
  local root="$tmp_dir/image-resume" bin="$tmp_dir/image-resume/bin" runtime image_id source_commit
  mkdir -p "$root/shared" "$root/state" "$root/data/mail/dkim" "$bin"
  stage_release "$root" release-image
  write_valid_environment "$root/shared/.env" image-resume
  printf 'private\n' > "$root/data/mail/dkim/designhub.private"
  printf 'record\n' > "$root/data/mail/dkim/designhub.txt"
  cat > "$bin/docker" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
if [[ "$1 $2" == 'image inspect' ]]; then
  if [[ "$*" == *--format* ]]; then
    case "$*" in
      *'printf'*'cn.design-hub.release-id'*) printf '%s\t%s\t%s\t%s\n' "$FAKE_IMAGE_ID" "$FAKE_LABEL_RELEASE" "$FAKE_LABEL_SOURCE" "$FAKE_LABEL_REPOSITORY" ;;
      *'.Id'*) printf '%s\n' "$FAKE_IMAGE_ID" ;;
      *'release-id'*) printf '%s\n' "$FAKE_LABEL_RELEASE" ;;
      *'source-commit'*) printf '%s\n' "$FAKE_LABEL_SOURCE" ;;
      *'image-repository'*) printf '%s\n' "$FAKE_LABEL_REPOSITORY" ;;
      *) exit 2 ;;
    esac
    exit 0
  fi
  [[ -f "$FAKE_IMAGE_EXISTS" ]]
  exit
fi
if [[ "$1" == build ]]; then
  iidfile=""
  dockerfile=""
  context="${*: -1}"
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --iidfile) iidfile="$2"; shift 2 ;;
      --file) dockerfile="$2"; shift 2 ;;
      *) shift ;;
    esac
  done
  [[ -n "$iidfile" ]] || exit 2
  [[ "$dockerfile" == "$EXPECTED_API_DOCKERFILE" ]] || exit 3
  [[ "$context" == "$EXPECTED_API_BUILD_CONTEXT" ]] || exit 4
  [[ -f "$dockerfile" ]] || exit 5
  printf '%s' "$FAKE_IMAGE_ID" > "$iidfile"
  : > "$FAKE_IMAGE_EXISTS"
  exit 0
fi
if [[ "$1" == compose ]]; then
  printf 'compose-reference=%s args=%s\n' "${API_IMAGE_REFERENCE:-tag}" "$*" >> "$FAKE_DOCKER_LOG"
  [[ "$*" != *' build '* ]] || : > "$FAKE_IMAGE_EXISTS"
  exit 0
fi
echo "unexpected docker invocation: $*" >&2; exit 2
SH
  cat > "$bin/python3" <<'SH'
#!/usr/bin/env bash
set -euo pipefail
cat >/dev/null
: > "$3"
SH
  chmod +x "$bin/docker" "$bin/python3"
  runtime="$root/releases/release-image/deploy/scripts/release-runtime.sh"
  image_id="sha256:$(printf 'a%.0s' {1..64})"
  source_commit="$(sed -n 's/^SOURCE_COMMIT=//p' "$root/releases/release-image/release.env")"
  export FAKE_LABEL_RELEASE=release-image FAKE_LABEL_SOURCE="$source_commit" FAKE_LABEL_REPOSITORY=design-hub-api
  export FAKE_DOCKER_LOG="$root/docker.log"
  export EXPECTED_API_DOCKERFILE="$root/releases/release-image/deploy/app/Dockerfile"
  export EXPECTED_API_BUILD_CONTEXT="$root/releases/release-image/app"
  PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" FAKE_IMAGE_EXISTS="$root/image.exists" FAKE_IMAGE_ID="$image_id" \
    bash "$runtime" build-release "$root/releases/release-image" release-image || fail "first immutable image build failed"
  rm "$root/state/image-identities/release-image.api"
  printf '%s\n' "$image_id" > "$root/state/image-identities/release-image.api.building"
  chmod 600 "$root/state/image-identities/release-image.api.building"
  if PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" FAKE_IMAGE_EXISTS="$root/image.exists" \
    FAKE_IMAGE_ID="sha256:$(printf 'b%.0s' {1..64})" \
    bash "$runtime" build-release "$root/releases/release-image" release-image; then
    fail "crash resume accepted a tag with a different image ID"
  fi
  PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" FAKE_IMAGE_EXISTS="$root/image.exists" FAKE_IMAGE_ID="$image_id" \
    bash "$runtime" build-release "$root/releases/release-image" release-image || fail "crash-before-identity image resume failed"
  if FAKE_LABEL_SOURCE=wrong-source PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" \
    FAKE_IMAGE_EXISTS="$root/image.exists" FAKE_IMAGE_ID="$image_id" \
    bash "$runtime" build-release "$root/releases/release-image" release-image; then
    fail "image resume accepted labels from another source manifest"
  fi
  if PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" FAKE_IMAGE_EXISTS="$root/image.exists" \
    FAKE_IMAGE_ID="sha256:$(printf 'b%.0s' {1..64})" bash "$runtime" build-release "$root/releases/release-image" release-image; then
    fail "image resume accepted a different immutable image"
  fi
  assert_file_mode_600 "$root/state/image-identities/release-image.api"
  PATH="$bin:$PATH" DEPLOY_ROOT="$root" DATA_DIR="$root/data" FAKE_IMAGE_EXISTS="$root/image.exists" FAKE_IMAGE_ID="$image_id" \
    bash "$runtime" migrate "$root/releases/release-image" release-image || fail "immutable image migration failed"
  grep -Fq "compose-reference=$image_id" "$root/docker.log" || fail "migrate consumed a mutable image tag"
  unset FAKE_LABEL_RELEASE FAKE_LABEL_SOURCE FAKE_LABEL_REPOSITORY FAKE_DOCKER_LOG \
    EXPECTED_API_DOCKERFILE EXPECTED_API_BUILD_CONTEXT
}

test_pending_recovery_closes_crash_state() {
  local remote_root="$tmp_dir/pending-recovery" recovery
  prepare_active_legacy "$remote_root"
  set_runtime_failures "$remote_root" 'health-live:release-b' 'start-release:release-a'
  if run_deploy "$remote_root" release-b "$remote_root/crash.log"; then fail "pending crash fixture unexpectedly succeeded"; fi
  recovery="$remote_root/releases/release-b/deploy/scripts/recover-pending-release.sh"
  [[ -x "$recovery" ]] || fail "pending recovery entry point is missing"
  if DEPLOY_ROOT="$remote_root" DATA_DIR="$remote_root/data" BACKUP_DIR="$remote_root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$remote_root/runtime.log" RUNTIME_FAIL_ONCE="$remote_root/fail-once" bash "$recovery" --candidate wrong --rollback-target release-a; then
    fail "pending recovery accepted wrong candidate identity"
  fi
  set_runtime_failure "$remote_root" health-public release-a
  if DEPLOY_ROOT="$remote_root" DATA_DIR="$remote_root/data" BACKUP_DIR="$remote_root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$remote_root/runtime.log" RUNTIME_FAIL_ONCE="$remote_root/fail-once" bash "$recovery" --candidate release-b --rollback-target release-a; then
    fail "pending recovery public failure unexpectedly succeeded"
  fi
  [[ "$(read_pending "$remote_root")" == release-b && -f "$remote_root/state/maintenance" ]] \
    || fail "failed pending recovery lost recoverable state"
  DEPLOY_ROOT="$remote_root" DATA_DIR="$remote_root/data" BACKUP_DIR="$remote_root/backups" RELEASE_RUNTIME="$fake_runtime" \
    RUNTIME_LOG="$remote_root/runtime.log" RUNTIME_FAIL_ONCE="$remote_root/fail-once" bash "$recovery" --candidate release-b --rollback-target release-a \
    || fail "valid pending recovery failed"
  [[ "$(read_active "$remote_root")" == release-a && -z "$(read_pending "$remote_root")" ]] || fail "pending recovery did not atomically resolve state"
}

test_legacy_split_state_is_rejected() {
  local remote_root="$tmp_dir/legacy-split"
  prepare_active_legacy "$remote_root"; rm "$remote_root/state/release-selection"; printf 'release-a\n' > "$remote_root/state/active-release"; chmod 600 "$remote_root/state/active-release"
  if run_deploy "$remote_root" release-b "$remote_root/deploy.log"; then fail "missing selection with legacy split state was accepted"; fi
  [[ ! -s "$remote_root/runtime.log" ]] || fail "legacy split state invoked runtime"
}

test_pending_selection_rejects_equal_active_previous() {
  local root="$tmp_dir/pending-invariant"
  mkdir -p "$root/state"
  # shellcheck source=release-state.sh
  source "$script_dir/release-state.sh"
  if atomic_write_release_selection "$root/state/release-selection" release-a release-a release-b; then
    fail "pending selection accepted active == previous"
  fi
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
if selected previous-env-failures; then
  test_previous_release_environment_failures_restore_bytes
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
if selected selection-state; then
  test_single_selection_state
fi
if selected invalid-identity-guard; then
  test_invalid_identity_arms_guard
fi
if selected public-hang; then
  test_public_probe_hang_is_bounded
fi
if selected docker-inspect-errors; then
  test_docker_inspect_errors_fail_fast
fi
if selected schema-protected-copy; then
  test_schema_uses_protected_copy
fi
if selected lock-recovery; then
  test_explicit_stale_lock_recovery
fi
if selected env-source-swap; then
  test_environment_source_swap_never_reaches_live
fi
if selected selection-write-failure; then
  test_selection_write_failure_is_atomic_and_retryable
fi
if selected lock-ownership; then
  test_lock_ownership_boundaries
fi
if selected env-destination-tamper; then
  test_environment_destination_tamper_restores_rescue
fi
if selected schema-protected-tamper; then
  test_protected_schema_tamper_is_rejected
fi
if selected snapshot-create-race; then test_snapshot_creation_rejects_changing_source; fi
if selected schema-final-consumer; then test_schema_final_consumer_is_fixed; fi
if selected hard-timeout; then test_timeout_kills_term_ignoring_tree; fi
if selected deploy-retry; then test_deploy_snapshot_initialization_is_retryable; fi
if selected partial-lock-recovery; then test_partial_lock_is_explicitly_recoverable; fi
if selected pending-recovery; then test_pending_recovery_closes_crash_state; fi
if selected legacy-split-reject; then test_legacy_split_state_is_rejected; fi
if selected pending-invariant; then test_pending_selection_rejects_equal_active_previous; fi
if selected partial-lock-types; then test_partial_lock_types_fail_closed; fi
if selected initial-pending-abort; then test_initial_pending_abort_is_explicit_and_safe; fi
if selected systemd-containment; then test_systemd_cgroup_boundary_is_required; fi
if selected final-commit-retry; then test_final_selection_commit_retry; fi
if selected dangling-state-reject; then test_dangling_release_state_is_rejected; fi
if selected image-resume-identity; then test_api_image_resume_is_manifest_bound; fi
if selected lock-tombstone; then test_lock_cleanup_uses_atomic_tombstone; fi
if selected runtime-contract; then test_runtime_contract_is_protected; fi

echo "release safety ${test_case}: OK"
