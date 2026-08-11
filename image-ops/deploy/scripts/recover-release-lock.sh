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
[[ "$(find "$lock_dir" -mindepth 1 -maxdepth 1 -printf '%f\n' | sort)" == owner ]] || {
  echo "ERROR: deployment lock contains unexpected files" >&2
  exit 1
}
load_lock_owner "$lock_dir" || {
  echo "ERROR: deployment lock owner metadata is invalid" >&2
  exit 1
}
if [[ "$(process_start_ticks "$lock_owner_pid")" == "$lock_owner_start_ticks" ]]; then
  echo "ERROR: deployment lock owner is still alive" >&2
  exit 1
fi
release_release_lock "$lock_dir" "$lock_owner_token"
echo "Recovered stale deployment lock owned by PID ${lock_owner_pid}."
