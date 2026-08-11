#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=release-state.sh
source "$script_dir/release-state.sh"

candidate=""
rollback_target=""
initial_abort=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --initial-abort) initial_abort=true; shift ;;
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
  if [[ "$status" -ne 0 ]] && ! atomic_enable_maintenance "$maintenance_file"; then
    echo "ERROR: failed to retain maintenance during pending recovery" >&2
    status=1
  fi
  if ! release_release_lock "$lock_dir" "$release_lock_token"; then [[ "$status" -ne 0 ]] || status=1; fi
  exit "$status"
}
trap cleanup EXIT
atomic_enable_maintenance "$maintenance_file"

require_release_id "$candidate" candidate
load_release_state "$selection_file"
[[ "$release_state_pending" == "$candidate" ]] || { echo "ERROR: pending recovery candidate mismatch" >&2; exit 1; }
if [[ "$initial_abort" == true ]]; then
  [[ -z "$rollback_target" ]] || { echo "ERROR: initial abort cannot specify a rollback target" >&2; exit 1; }
  [[ -z "$release_state_active" && -z "$release_state_previous" ]] \
    || { echo "ERROR: initial abort requires empty active and previous state" >&2; exit 1; }
  verify_bound_environment_snapshot "$state_dir/env-snapshots/$candidate.before.env" \
    "$state_dir/env-snapshots/$candidate.before.meta" "$candidate" ""
  candidate_dir="$deploy_root/releases/$candidate"
  [[ -d "$candidate_dir" && ! -L "$candidate_dir" ]] \
    || { echo "ERROR: initial abort candidate directory is invalid" >&2; exit 1; }
  candidate_manifest="$candidate_dir/release.env"
  [[ -f "$candidate_manifest" && ! -L "$candidate_manifest" ]] \
    || { echo "ERROR: initial abort candidate manifest is invalid" >&2; exit 1; }
  [[ "$(grep -c '^RELEASE_ID=' "$candidate_manifest" || true)" -eq 1 \
    && "$(sed -n 's/^RELEASE_ID=//p' "$candidate_manifest")" == "$candidate" ]] \
    || { echo "ERROR: initial abort candidate manifest identity mismatch" >&2; exit 1; }
  [[ "$(grep -c '^SOURCE_COMMIT=' "$candidate_manifest" || true)" -eq 1 ]] \
    || { echo "ERROR: initial abort candidate source identity is malformed" >&2; exit 1; }
  candidate_source="$(sed -n 's/^SOURCE_COMMIT=//p' "$candidate_manifest")"
  [[ "$candidate_source" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] \
    || { echo "ERROR: initial abort candidate source identity is invalid" >&2; exit 1; }
  runtime="${RELEASE_RUNTIME:-$candidate_dir/deploy/scripts/release-runtime.sh}"
  require_runtime_contract "$runtime"
  bash "$runtime" verify-application-owned "$candidate_dir" "$candidate"
  bash "$runtime" stop-application "$candidate_dir" "$candidate"
  bash "$runtime" verify-application-stopped "$candidate_dir" "$candidate"
  restore_bound_environment_snapshot "$state_dir/env-snapshots/$candidate.before.env" \
    "$state_dir/env-snapshots/$candidate.before.meta" "$deploy_root/shared/.env" "$candidate" ""
  atomic_write_release_selection "$selection_file" "" "" ""
  echo "==> INITIAL_PENDING_ABORT_DONE=${candidate}"
  exit 0
fi

require_release_id "$rollback_target" rollback-target
[[ "$candidate" != "$rollback_target" ]] || { echo "ERROR: pending candidate and rollback target must differ" >&2; exit 1; }
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
