#!/usr/bin/env bash
set -euo pipefail

[[ "${1:-}" == --confirm-stale-lock-recovery && $# -eq 1 ]] || {
  echo "usage: recover-release-lock.sh --confirm-stale-lock-recovery" >&2
  exit 2
}

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=release-state.sh
source "$script_dir/release-state.sh"

deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
lock_dir="$deploy_root/state/deploy.lock"
[[ -d "$lock_dir" && ! -L "$lock_dir" ]] || {
  echo "ERROR: no deployment lock is available for recovery" >&2
  exit 1
}
[[ "$(stat -c '%a' "$lock_dir")" == 700 ]] || {
  echo "ERROR: deployment lock directory permissions are invalid" >&2
  exit 1
}
if find "$lock_dir" -mindepth 1 -maxdepth 1 ! -name owner ! -name '.owner.*' -print -quit | grep -q .; then
  echo "ERROR: deployment lock contains unexpected files" >&2
  exit 1
fi
if [[ -e "$lock_dir/owner" ]]; then
  load_lock_owner "$lock_dir" || { echo "ERROR: deployment lock owner metadata is invalid" >&2; exit 1; }
  if [[ "$(process_start_ticks "$lock_owner_pid")" == "$lock_owner_start_ticks" ]]; then
    echo "ERROR: deployment lock owner is still alive" >&2; exit 1
  fi
  owner_token="$lock_owner_token"
  validate_lock_partials "$lock_dir" "$owner_token" || exit 1
else
  validate_lock_partials "$lock_dir" || exit 1
  [[ "$lock_partials_found" == true ]] || { echo "ERROR: ownerless deployment lock has no recoverable metadata" >&2; exit 1; }
fi
remove_lock_partials "$lock_dir" || exit 1
if [[ -e "$lock_dir/owner" ]]; then
  rm "$lock_dir/owner" || { echo "ERROR: failed to remove stale deployment lock owner" >&2; exit 1; }
fi
rmdir "$lock_dir" || { echo "ERROR: failed to remove recoverable deployment lock" >&2; exit 1; }
echo "Recovered stale or partial deployment lock."
