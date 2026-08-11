#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=release-state.sh
source "$script_dir/release-state.sh"

candidate=""
rollback_target=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --candidate) candidate="${2:?--candidate requires a release identifier}"; shift 2 ;;
    --rollback-target) rollback_target="${2:?--rollback-target requires a release identifier}"; shift 2 ;;
    *) echo "ERROR: unknown pending recovery argument: $1" >&2; exit 2 ;;
  esac
done

deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
state_dir="$deploy_root/state"
selection_file="$state_dir/release-selection"
maintenance_file="$state_dir/maintenance"
lock_dir="$state_dir/deploy.lock"

acquire_release_lock "$lock_dir" rollback
cleanup() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 ]]; then atomic_enable_maintenance "$maintenance_file" || true; fi
  if ! release_release_lock "$lock_dir" "$release_lock_token"; then [[ "$status" -ne 0 ]] || status=1; fi
  exit "$status"
}
trap cleanup EXIT
atomic_enable_maintenance "$maintenance_file"

require_release_id "$candidate" candidate
require_release_id "$rollback_target" rollback-target
[[ "$candidate" != "$rollback_target" ]] || { echo "ERROR: pending candidate and rollback target must differ" >&2; exit 1; }
load_release_state "$selection_file"
[[ "$release_state_pending" == "$candidate" ]] || { echo "ERROR: pending recovery candidate mismatch" >&2; exit 1; }
[[ "$release_state_active" == "$rollback_target" ]] || { echo "ERROR: pending recovery rollback target mismatch" >&2; exit 1; }
verify_bound_environment_snapshot "$state_dir/env-snapshots/$candidate.before.env" \
  "$state_dir/env-snapshots/$candidate.before.meta" "$candidate" "$rollback_target"

DEPLOY_ROOT="$deploy_root" DATA_DIR="${DATA_DIR:-/data/docker/design-hub}" \
  BACKUP_DIR="${BACKUP_DIR:-/root}" MYSQL_ENV="${MYSQL_ENV:-/opt/docker/mysql/.env}" \
  RELEASE_RUNTIME="${RELEASE_RUNTIME:-$deploy_root/releases/$rollback_target/deploy/scripts/release-runtime.sh}" \
  RELEASE_LOCK_TOKEN="$release_lock_token" \
  bash "$deploy_root/releases/$candidate/deploy/scripts/rollback.sh" \
    --from "$candidate" --to "$rollback_target"

echo "==> PENDING_RECOVERY_DONE=${candidate}->${rollback_target}"
