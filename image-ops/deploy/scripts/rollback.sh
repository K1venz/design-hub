#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=release-state.sh
source "$script_dir/release-state.sh"

from_release=""
to_release=""
schema_backup=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from)
      from_release="${2:?--from requires a release identifier}"
      shift 2
      ;;
    --to)
      to_release="${2:?--to requires a release identifier}"
      shift 2
      ;;
    --schema-backup)
      schema_backup="${2:?--schema-backup requires a path}"
      shift 2
      ;;
    *)
      echo "ERROR: unknown rollback argument: $1" >&2
      exit 2
      ;;
  esac
done

deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
data_dir="${DATA_DIR:-/data/docker/design-hub}"
backup_dir="${BACKUP_DIR:-/root}"
mysql_env="${MYSQL_ENV:-/opt/docker/mysql/.env}"
from_dir="$deploy_root/releases/$from_release"
target_dir="$deploy_root/releases/$to_release"
shared_dir="$deploy_root/shared"
state_dir="$deploy_root/state"
env_file="$shared_dir/.env"
maintenance_file="$state_dir/maintenance"
selection_file="$state_dir/release-selection"
snapshot_file="$state_dir/env-snapshots/$from_release.before.env"
snapshot_metadata_file="$state_dir/env-snapshots/$from_release.before.meta"
lock_dir="$state_dir/deploy.lock"

owns_lock=false
automatic_rollback=false
protected_schema_backup=""
protected_schema_digest=""
if [[ -n "${RELEASE_LOCK_TOKEN:-}" ]]; then
  borrow_release_lock "$lock_dir" "$RELEASE_LOCK_TOKEN"
  automatic_rollback=true
else
  acquire_release_lock "$lock_dir" rollback
  owns_lock=true
fi

maintenance_guard_armed=true
cleanup() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$maintenance_guard_armed" == true ]]; then
    if ! atomic_enable_maintenance "$maintenance_file"; then
      echo "ERROR: failed to restore maintenance protection" >&2
    fi
    echo "ERROR: rollback failed; maintenance remains enabled" >&2
  fi
  if [[ "$owns_lock" == true ]]; then
    if ! release_release_lock "$lock_dir" "$release_lock_token"; then
      [[ "$status" -ne 0 ]] || status=1
    fi
  fi
  [[ -z "$protected_schema_backup" || ! -e "$protected_schema_backup" ]] || rm -f "$protected_schema_backup" || {
    echo "ERROR: failed to remove protected schema input" >&2
    [[ "$status" -ne 0 ]] || status=1
  }
  exit "$status"
}
trap cleanup EXIT

atomic_enable_maintenance "$maintenance_file"
require_release_id "$from_release" from
require_release_id "$to_release" to
[[ "$from_release" != "$to_release" ]] || {
  echo "ERROR: rollback source and target must differ" >&2
  exit 1
}

for release_identity in "$from_release" "$to_release"; do
  if [[ "$release_identity" == "$from_release" ]]; then
    release_path="$from_dir"
  else
    release_path="$target_dir"
  fi
  [[ -f "$release_path/release.env" \
    && -f "$release_path/deploy/compose.yml" \
    && -f "$release_path/web/index.html" ]] || {
    echo "ERROR: rollback release ${release_identity} is incomplete" >&2
    exit 1
  }
  grep -Fxq "RELEASE_ID=${release_identity}" "$release_path/release.env" || {
    echo "ERROR: rollback release manifest identity mismatch" >&2
    exit 1
  }
done
unset release_identity release_path

if [[ -n "$schema_backup" ]]; then
  [[ "$schema_backup" == /* ]] || {
    echo "ERROR: schema backup path must be absolute" >&2
    exit 1
  }
  [[ -f "$schema_backup" && ! -L "$schema_backup" ]] || {
    echo "ERROR: schema backup must be a regular file" >&2
    exit 1
  }
  [[ "$(stat -c '%a' "$schema_backup")" == 600 ]] || {
    echo "ERROR: schema backup permissions must be 600" >&2
    exit 1
  }
  backup_root_resolved="$(realpath "$backup_dir")"
  schema_backup_resolved="$(realpath "$schema_backup")"
  case "$schema_backup_resolved" in
    "$backup_root_resolved"/*)
      ;;
    *)
      echo "ERROR: schema backup must stay inside BACKUP_DIR" >&2
      exit 1
      ;;
  esac
  schema_backup="$schema_backup_resolved"
  schema_input_dir="$state_dir/schema-restore-inputs"
  mkdir -p "$schema_input_dir"
  [[ -d "$schema_input_dir" && ! -L "$schema_input_dir" ]] || { echo "ERROR: protected schema input directory is unsafe" >&2; exit 1; }
  chmod 700 "$schema_input_dir"
  [[ "$(stat -c '%a' "$schema_input_dir")" == 700 ]] || { echo "ERROR: protected schema input directory permissions are unsafe" >&2; exit 1; }
  protected_schema_backup="$(mktemp "$schema_input_dir/restore.XXXXXX.sql")"
  source_identity="$(stat -Lc '%d:%i' "$schema_backup")"
  exec {schema_fd}< "$schema_backup"
  fd_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/$schema_fd")"
  [[ "$source_identity" == "$fd_identity" ]] || { echo "ERROR: schema backup changed while being opened" >&2; exit 1; }
  fd_before="$(stat -Lc '%d:%i:%s:%y:%z' "/proc/$$/fd/$schema_fd")"
  cat <&$schema_fd > "$protected_schema_backup"
  fd_after="$(stat -Lc '%d:%i:%s:%y:%z' "/proc/$$/fd/$schema_fd")"
  exec {schema_fd}<&-
  [[ "$fd_before" == "$fd_after" ]] || { echo "ERROR: schema backup changed while being copied" >&2; exit 1; }
  chmod 400 "$protected_schema_backup"
  [[ -s "$protected_schema_backup" && -f "$protected_schema_backup" && ! -L "$protected_schema_backup" ]] || { echo "ERROR: protected schema input is invalid" >&2; exit 1; }
  protected_schema_digest="$(sha256sum "$protected_schema_backup" | cut -d' ' -f1)"
  unset backup_root_resolved schema_backup_resolved
fi

load_release_state "$selection_file"
verify_bound_environment_snapshot \
  "$snapshot_file" "$snapshot_metadata_file" "$from_release" "$to_release"
resolve_release_rollback_target "$state_dir" "$target_dir" "$to_release"
target_previous_release="$release_rollback_target"

if [[ "$automatic_rollback" == true ]]; then
  [[ "$release_state_pending" == "$from_release" ]] || {
    echo "ERROR: automatic rollback pending release mismatch" >&2
    exit 1
  }
  [[ "$release_state_active" == "$to_release" ]] || {
    echo "ERROR: automatic rollback active release mismatch" >&2
    exit 1
  }
  if [[ "$release_state_previous" != "$target_previous_release" \
    && "$release_state_previous" != "$to_release" ]]; then
    echo "ERROR: automatic rollback previous release state mismatch" >&2
    exit 1
  fi
else
  [[ -z "$release_state_pending" ]] || {
    echo "ERROR: manual rollback is unavailable during a pending deployment" >&2
    exit 1
  }
  [[ "$release_state_active" == "$from_release" ]] || {
    echo "ERROR: manual rollback active release mismatch" >&2
    exit 1
  }
  [[ "$release_state_previous" == "$to_release" ]] || {
    echo "ERROR: manual rollback target is not the recorded previous release" >&2
    exit 1
  }
fi

runtime="${RELEASE_RUNTIME:-$target_dir/deploy/scripts/release-runtime.sh}"
bash "$runtime" enable-maintenance "$target_dir" "$to_release"
restore_bound_environment_snapshot \
  "$snapshot_file" "$snapshot_metadata_file" "$env_file" \
  "$from_release" "$to_release"

if [[ -n "$schema_backup" ]]; then
  bash "$runtime" stop-application "$target_dir" "$to_release"
  bash "$runtime" verify-application-stopped "$target_dir" "$to_release"
  [[ "$(sha256sum "$protected_schema_backup" | cut -d' ' -f1)" == "$protected_schema_digest" ]] || { echo "ERROR: protected schema input digest mismatch" >&2; exit 1; }
  bash "$runtime" restore-schema "$target_dir" "$to_release" "$protected_schema_backup"
fi

bash "$runtime" start-release "$target_dir" "$to_release"
bash "$runtime" health-candidate "$target_dir" "$to_release"
bash "$runtime" switch-web "$target_dir" "$to_release"
bash "$runtime" health-live "$target_dir" "$to_release"
atomic_state_remove "$maintenance_file"
connect_timeout="${PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS:-3}"
max_timeout="${PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS:-10}"
[[ "$connect_timeout" =~ ^[1-9][0-9]*$ && "$connect_timeout" -le 30 ]] || { echo "ERROR: invalid public health connect timeout" >&2; exit 1; }
[[ "$max_timeout" =~ ^[1-9][0-9]*$ && "$max_timeout" -le 120 ]] || { echo "ERROR: invalid public health max timeout" >&2; exit 1; }
PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS="$connect_timeout" PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS="$max_timeout" \
  timeout --signal=TERM "$max_timeout" bash "$runtime" health-public "$target_dir" "$to_release"

atomic_write_release_selection "$selection_file" "$to_release" "$target_previous_release" ""
[[ -z "$protected_schema_backup" ]] || rm -f "$protected_schema_backup"
maintenance_guard_armed=false
echo "==> ROLLBACK_DONE=${to_release}"
