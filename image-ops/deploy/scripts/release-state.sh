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
  [[ -e "$selection_file" ]] || return 0
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
  mkdir "$lock_dir" 2>/dev/null || { echo "ERROR: another release operation holds ${lock_dir}" >&2; return 1; }
  chmod 700 "$lock_dir" || { rmdir "$lock_dir"; return 1; }
  temporary="$(mktemp "$lock_dir/.owner.XXXXXX")" || { rmdir "$lock_dir"; return 1; }
  release_lock_token="$(openssl rand -hex 32)" || { rmdir "$lock_dir"; return 1; }
  release_lock_start_ticks="$(process_start_ticks $$)" || { rmdir "$lock_dir"; return 1; }
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

borrow_release_lock() {
  local lock_dir="$1" expected_token="$2"
  load_lock_owner "$lock_dir" || { echo "ERROR: deployment lock owner metadata is invalid" >&2; return 1; }
  [[ -n "$expected_token" && "$expected_token" == "$lock_owner_token" ]] || { echo "ERROR: deployment lock ownership token mismatch" >&2; return 1; }
  [[ "$(process_start_ticks "$lock_owner_pid")" == "$lock_owner_start_ticks" ]] || { echo "ERROR: deployment lock owner is no longer alive" >&2; return 1; }
  release_lock_token="$expected_token"
}

release_release_lock() {
  local lock_dir="$1" expected_token="$2"
  load_lock_owner "$lock_dir" || { echo "ERROR: cannot validate deployment lock for cleanup" >&2; return 1; }
  [[ "$expected_token" == "$lock_owner_token" ]] || { echo "ERROR: refusing to remove a lock owned by another operation" >&2; return 1; }
  rm "$lock_dir/owner" && rmdir "$lock_dir" || { echo "ERROR: failed to remove deployment lock" >&2; return 1; }
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
  [[ ! -e "$snapshot_file" && ! -L "$snapshot_file" \
    && ! -e "$metadata_file" && ! -L "$metadata_file" ]] || {
    echo "ERROR: environment snapshot already exists for immutable release ${candidate_release}" >&2
    return 1
  }

  snapshot_dir="$(dirname "$snapshot_file")"
  mkdir -p "$snapshot_dir"
  snapshot_temporary="${snapshot_file}.tmp.$$"
  metadata_temporary="${metadata_file}.tmp.$$"
  umask 077
  if ! cp "$source_file" "$snapshot_temporary" \
    || ! chmod 600 "$snapshot_temporary"; then
    rm -f "$snapshot_temporary" "$metadata_temporary"
    return 1
  fi
  digest="$(sha256sum "$snapshot_temporary" | cut -d' ' -f1)"
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
