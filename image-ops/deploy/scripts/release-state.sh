#!/usr/bin/env bash

release_id_is_valid() {
  local release_id="$1"
  [[ "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]
}

require_release_id() {
  local release_id="$1"
  local label="$2"
  release_id_is_valid "$release_id" || {
    echo "ERROR: invalid ${label} release identifier" >&2
    return 1
  }
}

require_runtime_contract() {
  local runtime="$1" mode
  [[ "$runtime" == /* ]] || { echo "ERROR: release runtime path must be absolute" >&2; return 1; }
  [[ -f "$runtime" && ! -L "$runtime" && -x "$runtime" ]] \
    || { echo "ERROR: release runtime must be an executable regular file" >&2; return 1; }
  mode="$(stat -c '%a' "$runtime")" || return 1
  (( (8#$mode & 8#022) == 0 )) \
    || { echo "ERROR: release runtime must not be group- or world-writable" >&2; return 1; }
}

atomic_state_write() {
  local destination="$1"
  local value="$2"
  local temporary="${destination}.tmp.$$"
  umask 077
  if ! printf '%s\n' "$value" > "$temporary" \
    || ! chmod 600 "$temporary" \
    || ! mv -f "$temporary" "$destination"; then
    rm -f "$temporary"
    return 1
  fi
}

atomic_state_remove() { rm -f "$1"; }

atomic_enable_maintenance() {
  local maintenance_file="$1"
  local temporary
  temporary="$(mktemp "$(dirname "$maintenance_file")/.maintenance.XXXXXX")" || return 1
  umask 077
  if ! : > "$temporary" \
    || ! chmod 600 "$temporary" \
    || ! mv -f "$temporary" "$maintenance_file"; then
    rm -f "$temporary"
    return 1
  fi
}

load_release_state() {
  local selection_file="$1" line unknown
  release_state_active=""; release_state_previous=""; release_state_pending=""
  if [[ ! -e "$selection_file" && ! -L "$selection_file" ]]; then
    local state_dir
    state_dir="$(dirname "$selection_file")"
    if [[ -e "$state_dir/active-release" || -L "$state_dir/active-release" \
      || -e "$state_dir/previous-release" || -L "$state_dir/previous-release" \
      || -e "$state_dir/pending-release" || -L "$state_dir/pending-release" ]]; then
      echo "ERROR: legacy split release state exists without release-selection" >&2
      return 1
    fi
    return 0
  fi
  [[ -f "$selection_file" && ! -L "$selection_file" && "$(stat -c '%a' "$selection_file")" == 600 ]] || {
    echo "ERROR: release selection is not a protected regular file" >&2; return 1; }
  [[ "$(wc -l < "$selection_file")" -eq 4 ]] || { echo "ERROR: release selection is malformed" >&2; return 1; }
  unknown="$(grep -Evc '^(SELECTION_FORMAT|ACTIVE_RELEASE|PREVIOUS_RELEASE|PENDING_RELEASE)=' "$selection_file" || true)"
  [[ "$unknown" -eq 0 ]] || { echo "ERROR: release selection contains unknown fields" >&2; return 1; }
  [[ "$(grep -c '^SELECTION_FORMAT=1$' "$selection_file")" -eq 1 ]] || { echo "ERROR: unsupported release selection format" >&2; return 1; }
  for line in ACTIVE_RELEASE PREVIOUS_RELEASE PENDING_RELEASE; do
    [[ "$(grep -c "^${line}=" "$selection_file")" -eq 1 ]] || { echo "ERROR: duplicate release selection field" >&2; return 1; }
  done
  release_state_active="$(sed -n 's/^ACTIVE_RELEASE=//p' "$selection_file")"
  release_state_previous="$(sed -n 's/^PREVIOUS_RELEASE=//p' "$selection_file")"
  release_state_pending="$(sed -n 's/^PENDING_RELEASE=//p' "$selection_file")"
  [[ -z "$release_state_active" ]] || require_release_id "$release_state_active" active || return 1
  [[ -z "$release_state_previous" ]] || require_release_id "$release_state_previous" previous || return 1
  [[ -z "$release_state_pending" ]] || require_release_id "$release_state_pending" pending || return 1

  if [[ -z "$release_state_active" && -n "$release_state_previous" ]]; then
    echo "ERROR: previous release state exists without an active release" >&2
    return 1
  fi
  if [[ -n "$release_state_pending" \
    && "$release_state_pending" == "$release_state_active" ]]; then
    echo "ERROR: pending and active release identities conflict" >&2
    return 1
  fi
  if [[ -n "$release_state_pending" && -n "$release_state_previous" \
    && "$release_state_previous" == "$release_state_active" ]]; then
    echo "ERROR: pending selection cannot have identical active and previous releases" >&2
    return 1
  fi
  if [[ -z "$release_state_pending" \
    && -n "$release_state_previous" \
    && "$release_state_previous" == "$release_state_active" ]]; then
    echo "ERROR: active and previous release identities conflict" >&2
    return 1
  fi
}

atomic_write_release_selection() {
  local destination="$1" active="$2" previous="$3" pending="$4" temporary
  [[ -z "$active" ]] || require_release_id "$active" active || return 1
  [[ -z "$previous" ]] || require_release_id "$previous" previous || return 1
  [[ -z "$pending" ]] || require_release_id "$pending" pending || return 1
  [[ -z "$previous" || -n "$active" ]] || { echo "ERROR: previous release requires active release" >&2; return 1; }
  [[ -z "$pending" || "$pending" != "$active" ]] || { echo "ERROR: pending and active conflict" >&2; return 1; }
  [[ -z "$pending" || -z "$previous" || "$previous" != "$active" ]] || { echo "ERROR: pending selection cannot have identical active and previous releases" >&2; return 1; }
  [[ -n "$pending" || -z "$previous" || "$previous" != "$active" ]] || { echo "ERROR: active and previous conflict" >&2; return 1; }
  umask 077
  temporary="$(mktemp "$(dirname "$destination")/.release-selection.XXXXXX")" || return 1
  if ! printf '%s\n' 'SELECTION_FORMAT=1' "ACTIVE_RELEASE=$active" "PREVIOUS_RELEASE=$previous" "PENDING_RELEASE=$pending" > "$temporary" \
    || ! chmod 600 "$temporary" || ! mv -f "$temporary" "$destination"; then
    rm -f "$temporary"; return 1
  fi
}

process_start_ticks() { awk '{print $22}' "/proc/$1/stat" 2>/dev/null; }

acquire_release_lock() {
  local lock_dir="$1" operation="$2" owner temporary
  owner="$lock_dir/owner"
  release_lock_token="$(openssl rand -hex 32)" || return 1
  release_lock_start_ticks="$(process_start_ticks $$)" || return 1
  mkdir "$lock_dir" 2>/dev/null || { echo "ERROR: another release operation holds ${lock_dir}" >&2; return 1; }
  chmod 700 "$lock_dir" || { rmdir "$lock_dir"; return 1; }
  temporary="$(mktemp "$lock_dir/.owner.XXXXXX")" || { rmdir "$lock_dir"; return 1; }
  umask 077
  if ! printf '%s\n' 'LOCK_FORMAT=1' "TOKEN=$release_lock_token" "PID=$$" "START_TICKS=$release_lock_start_ticks" "OPERATION=$operation" > "$temporary" \
    || ! chmod 600 "$temporary" || ! mv -f "$temporary" "$owner"; then
    rm -f "$temporary"; rmdir "$lock_dir" 2>/dev/null || true; return 1
  fi
}

load_lock_owner() {
  local lock_dir="$1" owner
  owner="$lock_dir/owner"
  [[ -d "$lock_dir" && ! -L "$lock_dir" && "$(stat -c '%a' "$lock_dir")" == 700 ]] || return 1
  [[ -f "$owner" && ! -L "$owner" && "$(stat -c '%a' "$owner")" == 600 && "$(wc -l < "$owner")" -eq 5 ]] || return 1
  grep -Fxq 'LOCK_FORMAT=1' "$owner" || return 1
  lock_owner_token="$(sed -n 's/^TOKEN=//p' "$owner")"; [[ "$lock_owner_token" =~ ^[0-9a-f]{64}$ ]] || return 1
  lock_owner_pid="$(sed -n 's/^PID=//p' "$owner")"; [[ "$lock_owner_pid" =~ ^[1-9][0-9]*$ ]] || return 1
  lock_owner_start_ticks="$(sed -n 's/^START_TICKS=//p' "$owner")"; [[ "$lock_owner_start_ticks" =~ ^[0-9]+$ ]] || return 1
  lock_owner_operation="$(sed -n 's/^OPERATION=//p' "$owner")"; [[ "$lock_owner_operation" =~ ^(deploy|rollback)$ ]] || return 1
}

load_lock_metadata_file() {
  local metadata_file="$1"
  [[ -f "$metadata_file" && ! -L "$metadata_file" \
    && "$(stat -c '%a' "$metadata_file")" == 600 \
    && "$(wc -l < "$metadata_file")" -eq 5 ]] || return 1
  grep -Fxq 'LOCK_FORMAT=1' "$metadata_file" || return 1
  partial_lock_token="$(sed -n 's/^TOKEN=//p' "$metadata_file")"; [[ "$partial_lock_token" =~ ^[0-9a-f]{64}$ ]] || return 1
  partial_lock_pid="$(sed -n 's/^PID=//p' "$metadata_file")"; [[ "$partial_lock_pid" =~ ^[1-9][0-9]*$ ]] || return 1
  partial_lock_start_ticks="$(sed -n 's/^START_TICKS=//p' "$metadata_file")"; [[ "$partial_lock_start_ticks" =~ ^[0-9]+$ ]] || return 1
  partial_lock_operation="$(sed -n 's/^OPERATION=//p' "$metadata_file")"; [[ "$partial_lock_operation" =~ ^(deploy|rollback)$ ]] || return 1
}

validate_lock_partials() {
  local lock_dir="$1" expected_token="${2:-}" partial found=false
  shopt -s nullglob
  for partial in "$lock_dir"/.owner.*; do
    found=true
    load_lock_metadata_file "$partial" || { shopt -u nullglob; echo "ERROR: deployment lock partial metadata is invalid" >&2; return 1; }
    if [[ -n "$expected_token" ]]; then
      [[ "$partial_lock_token" == "$expected_token" \
        && "$partial_lock_pid" == "$lock_owner_pid" \
        && "$partial_lock_start_ticks" == "$lock_owner_start_ticks" \
        && "$partial_lock_operation" == "$lock_owner_operation" ]] \
        || { shopt -u nullglob; echo "ERROR: deployment lock partial ownership mismatch" >&2; return 1; }
    else
      [[ "$(process_start_ticks "$partial_lock_pid")" != "$partial_lock_start_ticks" ]] || { shopt -u nullglob; echo "ERROR: deployment lock partial owner is still alive" >&2; return 1; }
    fi
  done
  shopt -u nullglob
  lock_partials_found="$found"
}

remove_lock_partials() {
  local lock_dir="$1" partial
  shopt -s nullglob
  for partial in "$lock_dir"/.owner.*; do
    rm -- "$partial" || { shopt -u nullglob; echo "ERROR: failed to remove deployment lock partial" >&2; return 1; }
  done
  shopt -u nullglob
}

borrow_release_lock() {
  local lock_dir="$1" expected_token="$2"
  load_lock_owner "$lock_dir" || { echo "ERROR: deployment lock owner metadata is invalid" >&2; return 1; }
  [[ -n "$expected_token" && "$expected_token" == "$lock_owner_token" ]] || { echo "ERROR: deployment lock ownership token mismatch" >&2; return 1; }
  [[ "$(process_start_ticks "$lock_owner_pid")" == "$lock_owner_start_ticks" ]] || { echo "ERROR: deployment lock owner is no longer alive" >&2; return 1; }
  release_lock_token="$expected_token"
}

release_release_lock() {
  local lock_dir="$1" expected_token="$2" tombstone
  load_lock_owner "$lock_dir" || { echo "ERROR: cannot validate deployment lock for cleanup" >&2; return 1; }
  [[ "$expected_token" == "$lock_owner_token" ]] || { echo "ERROR: refusing to remove a lock owned by another operation" >&2; return 1; }
  if find "$lock_dir" -mindepth 1 -maxdepth 1 ! -name owner ! -name '.owner.*' -print -quit | grep -q .; then
    echo "ERROR: deployment lock contains unexpected files" >&2; return 1
  fi
  validate_lock_partials "$lock_dir" "$expected_token" || return 1
  tombstone="${lock_dir}.released.${expected_token}"
  [[ ! -e "$tombstone" && ! -L "$tombstone" ]] \
    || { echo "ERROR: deployment lock cleanup tombstone already exists" >&2; return 1; }
  mv -- "$lock_dir" "$tombstone" \
    || { echo "ERROR: failed to atomically retire deployment lock" >&2; return 1; }
  lock_dir="$tombstone"
  remove_lock_partials "$lock_dir" || return 1
  [[ -z "$(find "$lock_dir" -mindepth 1 -maxdepth 1 ! -name owner -print -quit)" ]] \
    || { echo "ERROR: deployment lock cleanup is incomplete" >&2; return 1; }
  rm "$lock_dir/owner" || { echo "ERROR: failed to remove deployment lock owner" >&2; return 1; }
  rmdir "$lock_dir" || { echo "ERROR: failed to remove deployment lock" >&2; return 1; }
}

stable_copy_regular_file() {
  local source_file="$1" destination="$2" mode="$3" source_identity fd_identity before after
  [[ -f "$source_file" && ! -L "$source_file" ]] || { echo "ERROR: source is not a regular file" >&2; return 1; }
  source_identity="$(stat -Lc '%d:%i' "$source_file")" || return 1
  exec {stable_fd}< "$source_file" || return 1
  fd_identity="$(stat -Lc '%d:%i' "/proc/$$/fd/$stable_fd")" || { exec {stable_fd}<&-; return 1; }
  [[ "$source_identity" == "$fd_identity" ]] || { exec {stable_fd}<&-; echo "ERROR: source changed while being opened" >&2; return 1; }
  before="$(stat -Lc '%d:%i:%s:%y:%z' "/proc/$$/fd/$stable_fd")"
  if ! cat <&$stable_fd > "$destination"; then exec {stable_fd}<&-; rm -f "$destination"; return 1; fi
  after="$(stat -Lc '%d:%i:%s:%y:%z' "/proc/$$/fd/$stable_fd")"
  exec {stable_fd}<&-
  if [[ "$before" != "$after" || "$(stat -Lc '%d:%i' "$source_file" 2>/dev/null || true)" != "$source_identity" ]]; then
    rm -f "$destination"; echo "ERROR: source changed while being copied" >&2; return 1
  fi
  chmod "$mode" "$destination"
}

run_with_hard_timeout() {
  local max_seconds="$1" leader watchdog status leader_win_pid="" timeout_marker unit_name key value
  local -a systemd_environment=()
  shift
  case "$(uname -s)" in
    MINGW*|MSYS*)
      timeout_marker="$(mktemp "${TMPDIR:-/tmp}/release-timeout.XXXXXX")" || return 1
      rm -f "$timeout_marker"
      "$@" & leader=$!
      leader_win_pid="$(ps | awk -v target="$leader" '$1 == target {print $4}')"
      ;;
    *)
      command -v systemd-run >/dev/null 2>&1 || { echo "ERROR: systemd-run is required for bounded public probes" >&2; return 1; }
      [[ -d /run/systemd/system || -n "${RELEASE_ALLOW_FAKE_SYSTEMD:-}" ]] \
        || { echo "ERROR: systemd is not the active service manager" >&2; return 1; }
      unit_name="design-hub-probe-$BASHPID-$(openssl rand -hex 6)"
      for key in PUBLIC_HEALTH_URL PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS \
        DEPLOY_ROOT DATA_DIR BACKUP_DIR MYSQL_ENV SERVER_IP API_IMAGE_REPOSITORY; do
        if [[ -v "$key" ]]; then
          value="${!key}"
          [[ "$value" != *$'\n'* && "$value" != *$'\r'* ]] \
            || { echo "ERROR: invalid newline in public probe environment" >&2; return 1; }
          systemd_environment+=("--setenv=${key}=${value}")
        fi
      done
      systemd-run --quiet --wait --collect --pipe --service-type=exec \
        "--unit=$unit_name" \
        '--working-directory=/' \
        "--property=RuntimeMaxSec=${max_seconds}s" \
        '--property=TimeoutStopSec=2s' \
        '--property=KillMode=control-group' \
        "${systemd_environment[@]}" \
        -- "$@"
      return $?
      ;;
  esac
  (
    sleep "$max_seconds"
    : > "$timeout_marker"
    if [[ -n "$leader_win_pid" ]]; then
      taskkill.exe /PID "$leader_win_pid" /T /F >/dev/null 2>&1 || true
      exit 0
    fi
    kill -TERM -- "-$leader" 2>/dev/null || true
    sleep 2
    kill -KILL -- "-$leader" 2>/dev/null || true
  ) &
  watchdog=$!
  if wait "$leader"; then status=0; else status=$?; fi
  kill "$watchdog" 2>/dev/null || true
  wait "$watchdog" 2>/dev/null || true
  if [[ -e "$timeout_marker" ]]; then rm -f "$timeout_marker"; return 124; fi
  rm -f "$timeout_marker"
  return "$status"
}

create_bound_environment_snapshot() {
  local source_file="$1"
  local snapshot_file="$2"
  local metadata_file="$3"
  local candidate_release="$4"
  local rollback_release="$5"
  local snapshot_dir
  local snapshot_temporary
  local metadata_temporary
  local digest

  require_release_id "$candidate_release" candidate || return 1
  if [[ -n "$rollback_release" ]]; then
    require_release_id "$rollback_release" rollback || return 1
    [[ "$rollback_release" != "$candidate_release" ]] || {
      echo "ERROR: environment snapshot cannot target its candidate release" >&2
      return 1
    }
  fi
  [[ -f "$source_file" && ! -L "$source_file" ]] || {
    echo "ERROR: environment file is not a regular file" >&2
    return 1
  }
  [[ "$(stat -c '%a' "$source_file")" == 600 ]] || {
    echo "ERROR: environment file permissions must be 600" >&2
    return 1
  }
  snapshot_dir="$(dirname "$snapshot_file")"
  mkdir -p "$snapshot_dir"
  snapshot_temporary="$(mktemp "$snapshot_dir/.snapshot.XXXXXX")"
  metadata_temporary="$(mktemp "$snapshot_dir/.metadata.XXXXXX")"
  umask 077
  if ! stable_copy_regular_file "$source_file" "$snapshot_temporary" 600; then
    rm -f "$snapshot_temporary" "$metadata_temporary"
    return 1
  fi
  digest="$(sha256sum "$snapshot_temporary" | cut -d' ' -f1)"
  if [[ -e "$snapshot_file" || -e "$metadata_file" ]]; then
    if [[ -e "$snapshot_file" && -e "$metadata_file" ]] \
      && verify_bound_environment_snapshot "$snapshot_file" "$metadata_file" "$candidate_release" "$rollback_release" \
      && [[ "$digest" == "$snapshot_metadata_digest" ]]; then
      rm -f "$snapshot_temporary" "$metadata_temporary"
      return 0
    fi
    rm -f "$snapshot_temporary" "$metadata_temporary"
    echo "ERROR: immutable environment snapshot conflicts with current source" >&2
    return 1
  fi
  if ! printf '%s\n' \
    'SNAPSHOT_FORMAT=1' \
    "CANDIDATE_RELEASE=${candidate_release}" \
    "ROLLBACK_RELEASE=${rollback_release}" \
    "SNAPSHOT_SHA256=${digest}" > "$metadata_temporary" \
    || ! chmod 600 "$metadata_temporary" \
    || ! mv -f "$snapshot_temporary" "$snapshot_file" \
    || ! mv -f "$metadata_temporary" "$metadata_file"; then
    rm -f "$snapshot_temporary" "$metadata_temporary" "$snapshot_file" "$metadata_file"
    return 1
  fi
  unset digest
}

read_snapshot_metadata_value() {
  local metadata_file="$1"
  local key="$2"
  local count
  count="$(grep -c "^${key}=" "$metadata_file" || true)"
  [[ "$count" -eq 1 ]] || {
    echo "ERROR: environment snapshot metadata is malformed" >&2
    return 1
  }
  snapshot_metadata_value="$(grep -E "^${key}=" "$metadata_file" | cut -d= -f2-)"
}

load_snapshot_metadata() {
  local metadata_file="$1"
  local unknown_count
  [[ -f "$metadata_file" && ! -L "$metadata_file" ]] || {
    echo "ERROR: environment snapshot metadata is unavailable" >&2
    return 1
  }
  [[ "$(stat -c '%a' "$metadata_file")" == 600 ]] || {
    echo "ERROR: environment snapshot metadata permissions must be 600" >&2
    return 1
  }
  [[ "$(wc -l < "$metadata_file")" -eq 4 ]] || {
    echo "ERROR: environment snapshot metadata is malformed" >&2
    return 1
  }
  unknown_count="$(grep -Evc \
    '^(SNAPSHOT_FORMAT|CANDIDATE_RELEASE|ROLLBACK_RELEASE|SNAPSHOT_SHA256)=' \
    "$metadata_file" || true)"
  [[ "$unknown_count" -eq 0 ]] || {
    echo "ERROR: environment snapshot metadata contains unknown fields" >&2
    return 1
  }

  read_snapshot_metadata_value "$metadata_file" SNAPSHOT_FORMAT || return 1
  snapshot_metadata_format="$snapshot_metadata_value"
  read_snapshot_metadata_value "$metadata_file" CANDIDATE_RELEASE || return 1
  snapshot_metadata_candidate="$snapshot_metadata_value"
  read_snapshot_metadata_value "$metadata_file" ROLLBACK_RELEASE || return 1
  snapshot_metadata_rollback="$snapshot_metadata_value"
  read_snapshot_metadata_value "$metadata_file" SNAPSHOT_SHA256 || return 1
  snapshot_metadata_digest="$snapshot_metadata_value"

  [[ "$snapshot_metadata_format" == 1 ]] || {
    echo "ERROR: unsupported environment snapshot metadata format" >&2
    return 1
  }
  require_release_id "$snapshot_metadata_candidate" snapshot-candidate || return 1
  if [[ -n "$snapshot_metadata_rollback" ]]; then
    require_release_id "$snapshot_metadata_rollback" snapshot-rollback || return 1
    [[ "$snapshot_metadata_rollback" != "$snapshot_metadata_candidate" ]] || {
      echo "ERROR: environment snapshot cannot target its candidate release" >&2
      return 1
    }
  fi
  [[ "$snapshot_metadata_digest" =~ ^[0-9a-f]{64}$ ]] || {
    echo "ERROR: environment snapshot digest is malformed" >&2
    return 1
  }
}

verify_environment_snapshot_for_candidate() {
  local snapshot_file="$1"
  local metadata_file="$2"
  local expected_candidate="$3"
  local actual_digest
  require_release_id "$expected_candidate" candidate || return 1
  [[ -f "$snapshot_file" && ! -L "$snapshot_file" ]] || {
    echo "ERROR: environment snapshot is unavailable" >&2
    return 1
  }
  [[ "$(stat -c '%a' "$snapshot_file")" == 600 ]] || {
    echo "ERROR: environment snapshot permissions must be 600" >&2
    return 1
  }
  load_snapshot_metadata "$metadata_file" || return 1
  [[ "$snapshot_metadata_candidate" == "$expected_candidate" ]] || {
    echo "ERROR: environment snapshot candidate identity mismatch" >&2
    return 1
  }
  actual_digest="$(sha256sum "$snapshot_file" | cut -d' ' -f1)"
  [[ "$actual_digest" == "$snapshot_metadata_digest" ]] || {
    echo "ERROR: environment snapshot digest mismatch" >&2
    return 1
  }
  unset actual_digest
}

verify_bound_environment_snapshot() {
  local snapshot_file="$1"
  local metadata_file="$2"
  local expected_candidate="$3"
  local expected_rollback="$4"
  verify_environment_snapshot_for_candidate \
    "$snapshot_file" "$metadata_file" "$expected_candidate" || return 1
  [[ "$snapshot_metadata_rollback" == "$expected_rollback" ]] || {
    echo "ERROR: environment snapshot rollback identity mismatch" >&2
    return 1
  }
}

restore_bound_environment_snapshot() {
  local snapshot_file="$1"
  local metadata_file="$2"
  local destination_file="$3"
  local expected_candidate="$4"
  local expected_rollback="$5"
  local destination_dir temporary rescue
  local restored_digest rescue_digest=""
  destination_dir="$(dirname "$destination_file")"
  temporary="$(mktemp "$destination_dir/.env.restore.XXXXXX")" || return 1
  rescue="$(mktemp "$destination_dir/.env.rescue.XXXXXX")" || { rm -f "$temporary"; return 1; }
  umask 077
  if ! cp -- "$snapshot_file" "$temporary" || ! chmod 600 "$temporary"; then
    rm -f "$temporary" "$rescue"; return 1
  fi
  verify_bound_environment_snapshot "$temporary" "$metadata_file" \
    "$expected_candidate" "$expected_rollback" || { rm -f "$temporary" "$rescue"; return 1; }
  if [[ -e "$destination_file" ]]; then
    [[ -f "$destination_file" && ! -L "$destination_file" ]] || { rm -f "$temporary" "$rescue"; return 1; }
    cp -- "$destination_file" "$rescue" && chmod 600 "$rescue" || { rm -f "$temporary" "$rescue"; return 1; }
    rescue_digest="$(sha256sum "$rescue" | cut -d' ' -f1)"
  else
    rm -f "$rescue"
  fi
  if ! mv -f "$temporary" "$destination_file"; then
    rm -f "$temporary" "$rescue"
    return 1
  fi
  restored_digest="$(sha256sum "$destination_file" | cut -d' ' -f1)"
  [[ "$restored_digest" == "$snapshot_metadata_digest" ]] || {
    echo "ERROR: restored environment digest mismatch" >&2
    if [[ -e "$rescue" ]]; then
      if ! mv -f "$rescue" "$destination_file" \
        || [[ "$(sha256sum "$destination_file" | cut -d' ' -f1)" != "$rescue_digest" ]]; then
        rm -f "$destination_file"
        echo "ERROR: failed to restore protected environment after verification failure" >&2
      fi
    else
      rm -f "$destination_file"
    fi
    return 1
  }
  rm -f "$rescue"
  unset restored_digest
}

resolve_release_rollback_target() {
  local state_dir="$1"
  local release_dir="$2"
  local release_id="$3"
  local snapshot_file="$state_dir/env-snapshots/$release_id.before.env"
  local metadata_file="$state_dir/env-snapshots/$release_id.before.meta"
  require_release_id "$release_id" active || return 1
  release_rollback_target=""

  if [[ ! -e "$snapshot_file" && ! -e "$metadata_file" ]]; then
    grep -Fxq 'SOURCE_COMMIT=legacy-import' "$release_dir/release.env" || {
      echo "ERROR: release ${release_id} has no bound environment snapshot" >&2
      return 1
    }
    return 0
  fi
  [[ -e "$snapshot_file" && -e "$metadata_file" ]] || {
    echo "ERROR: release ${release_id} has incomplete environment snapshot state" >&2
    return 1
  }
  verify_environment_snapshot_for_candidate \
    "$snapshot_file" "$metadata_file" "$release_id" || return 1
  release_rollback_target="$snapshot_metadata_rollback"
}
