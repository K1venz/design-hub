#!/usr/bin/env bash
set -euo pipefail

from_release=""
to_release=""
env_snapshot=""
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
    --env-snapshot)
      env_snapshot="${2:?--env-snapshot requires a path}"
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

[[ "$from_release" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]
[[ "$to_release" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]

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
lock_dir="$state_dir/deploy.lock"

[[ -f "$target_dir/release.env" && -f "$target_dir/deploy/compose.yml" ]]
grep -Fxq "RELEASE_ID=${to_release}" "$target_dir/release.env"
if [[ -z "$env_snapshot" ]]; then
  env_snapshot="$state_dir/env-snapshots/$from_release.before.env"
fi
[[ -f "$env_snapshot" ]] || {
  echo "ERROR: rollback environment snapshot is unavailable" >&2
  exit 1
}

owns_lock=false
if [[ "${ROLLBACK_LOCK_HELD:-false}" != true ]]; then
  if ! mkdir "$lock_dir" 2>/dev/null; then
    echo "ERROR: another release operation holds ${lock_dir}" >&2
    exit 1
  fi
  owns_lock=true
fi

cleanup() {
  local status=$?
  trap - EXIT
  if [[ "$owns_lock" == true ]]; then
    rmdir "$lock_dir" 2>/dev/null || true
  fi
  if [[ "$status" -ne 0 ]]; then
    echo "ERROR: rollback failed; maintenance remains enabled" >&2
  fi
  exit "$status"
}
trap cleanup EXIT

atomic_state_write() {
  local destination="$1"
  local value="$2"
  local temporary="${destination}.tmp.$$"
  printf '%s\n' "$value" > "$temporary"
  mv -f "$temporary" "$destination"
}

runtime="${RELEASE_RUNTIME:-$target_dir/deploy/scripts/release-runtime.sh}"
ENV_FILE="$env_file"
export ENV_FILE
# shellcheck source=mail-env.sh
source "$from_dir/deploy/scripts/mail-env.sh"

touch "$maintenance_file"
restore_environment "$env_snapshot" "$env_file"
bash "$runtime" enable-maintenance "$target_dir" "$to_release"
if [[ -n "$schema_backup" ]]; then
  bash "$runtime" restore-schema "$target_dir" "$to_release" "$schema_backup"
fi
bash "$runtime" start-release "$target_dir" "$to_release"
bash "$runtime" health-candidate "$target_dir" "$to_release"
atomic_state_write "$active_file" "$to_release"
bash "$runtime" switch-web "$target_dir" "$to_release"
bash "$runtime" health-live "$target_dir" "$to_release"
rm -f "$maintenance_file"
bash "$runtime" health-public "$target_dir" "$to_release"
atomic_state_write "$previous_file" "$from_release"
echo "==> ROLLBACK_DONE=${to_release}"
