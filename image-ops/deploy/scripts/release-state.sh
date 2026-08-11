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

atomic_state_remove() {
  local destination="$1"
  rm -f "$destination"
}

atomic_promote_pending_release() {
  local pending_file="$1"
  local active_file="$2"
  local expected_release="$3"
  local pending_release
  read_release_state_file "$pending_file" pending || return 1
  pending_release="$release_state_value"
  [[ "$pending_release" == "$expected_release" ]] || {
    echo "ERROR: pending release state changed before activation" >&2
    return 1
  }
  mv -f "$pending_file" "$active_file"
}

atomic_enable_maintenance() {
  local maintenance_file="$1"
  local temporary="${maintenance_file}.tmp.$$"
  umask 077
  if ! : > "$temporary" \
    || ! chmod 600 "$temporary" \
    || ! mv -f "$temporary" "$maintenance_file"; then
    rm -f "$temporary"
    return 1
  fi
}

read_release_state_file() {
  local state_file="$1"
  local label="$2"
  release_state_value=""
  [[ -e "$state_file" ]] || return 0
  [[ -f "$state_file" && ! -L "$state_file" ]] || {
    echo "ERROR: ${label} release state is not a regular file" >&2
    return 1
  }
  [[ "$(wc -l < "$state_file")" -eq 1 ]] || {
    echo "ERROR: ${label} release state is malformed" >&2
    return 1
  }
  release_state_value="$(cat "$state_file")"
  require_release_id "$release_state_value" "$label"
}

load_release_state() {
  local active_file="$1"
  local previous_file="$2"
  local pending_file="$3"
  read_release_state_file "$active_file" active || return 1
  release_state_active="$release_state_value"
  read_release_state_file "$previous_file" previous || return 1
  release_state_previous="$release_state_value"
  read_release_state_file "$pending_file" pending || return 1
  release_state_pending="$release_state_value"

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
  local temporary="${destination_file}.restore.$$"
  local restored_digest
  verify_bound_environment_snapshot \
    "$snapshot_file" "$metadata_file" \
    "$expected_candidate" "$expected_rollback" || return 1
  umask 077
  if ! cp "$snapshot_file" "$temporary" \
    || ! chmod 600 "$temporary" \
    || ! mv -f "$temporary" "$destination_file"; then
    rm -f "$temporary"
    return 1
  fi
  restored_digest="$(sha256sum "$destination_file" | cut -d' ' -f1)"
  [[ "$restored_digest" == "$snapshot_metadata_digest" ]] || {
    echo "ERROR: restored environment digest mismatch" >&2
    return 1
  }
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
