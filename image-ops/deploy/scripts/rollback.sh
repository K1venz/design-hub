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

require_release_id "$from_release" from
require_release_id "$to_release" to
[[ "$from_release" != "$to_release" ]] || {
  echo "ERROR: rollback source and target must differ" >&2
  exit 1
}

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
active_file="$state_dir/active-release"
previous_file="$state_dir/previous-release"
pending_file="$state_dir/pending-release"
snapshot_file="$state_dir/env-snapshots/$from_release.before.env"
snapshot_metadata_file="$state_dir/env-snapshots/$from_release.before.meta"
lock_dir="$state_dir/deploy.lock"

owns_lock=false
automatic_rollback=false
if [[ "${ROLLBACK_LOCK_HELD:-false}" == true ]]; then
  [[ -d "$lock_dir" ]] || {
    echo "ERROR: automatic rollback requires the deployment lock" >&2
    exit 1
  }
  automatic_rollback=true
else
  if ! mkdir "$lock_dir" 2>/dev/null; then
    echo "ERROR: another release operation holds ${lock_dir}" >&2
    exit 1
  fi
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
    rmdir "$lock_dir" 2>/dev/null || true
  fi
  exit "$status"
}
trap cleanup EXIT

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
  unset backup_root_resolved schema_backup_resolved
fi

load_release_state "$active_file" "$previous_file" "$pending_file"
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
atomic_enable_maintenance "$maintenance_file"
bash "$runtime" enable-maintenance "$target_dir" "$to_release"
restore_bound_environment_snapshot \
  "$snapshot_file" "$snapshot_metadata_file" "$env_file" \
  "$from_release" "$to_release"

if [[ -n "$schema_backup" ]]; then
  bash "$runtime" stop-application "$target_dir" "$to_release"
  bash "$runtime" verify-application-stopped "$target_dir" "$to_release"
  bash "$runtime" restore-schema "$target_dir" "$to_release" "$schema_backup"
fi

bash "$runtime" start-release "$target_dir" "$to_release"
bash "$runtime" health-candidate "$target_dir" "$to_release"
bash "$runtime" switch-web "$target_dir" "$to_release"
bash "$runtime" health-live "$target_dir" "$to_release"
atomic_state_remove "$maintenance_file"
bash "$runtime" health-public "$target_dir" "$to_release"

if [[ -n "$target_previous_release" ]]; then
  atomic_state_write "$previous_file" "$target_previous_release"
else
  atomic_state_remove "$previous_file"
fi
if [[ "$automatic_rollback" == true ]]; then
  atomic_state_remove "$pending_file"
else
  atomic_state_write "$active_file" "$to_release"
fi
maintenance_guard_armed=false
echo "==> ROLLBACK_DONE=${to_release}"
