#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
# shellcheck source=release-state.sh
source "$script_dir/release-state.sh"

release_id="${1:?usage: deploy.sh RELEASE_ID}"
require_release_id "$release_id" candidate

deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
data_dir="${DATA_DIR:-/data/docker/design-hub}"
backup_dir="${BACKUP_DIR:-/root}"
mysql_env="${MYSQL_ENV:-/opt/docker/mysql/.env}"
release_dir="$deploy_root/releases/$release_id"
shared_dir="$deploy_root/shared"
state_dir="$deploy_root/state"
env_file="$shared_dir/.env"
active_file="$state_dir/active-release"
previous_file="$state_dir/previous-release"
pending_file="$state_dir/pending-release"
maintenance_file="$state_dir/maintenance"
snapshot_file="$state_dir/env-snapshots/$release_id.before.env"
snapshot_metadata_file="$state_dir/env-snapshots/$release_id.before.meta"
lock_dir="$state_dir/deploy.lock"

for required in "$release_dir/release.env" "$release_dir/deploy/compose.yml" \
  "$release_dir/deploy/scripts/mail-env.sh" \
  "$release_dir/deploy/scripts/release-state.sh" \
  "$release_dir/deploy/scripts/rollback.sh" \
  "$release_dir/web/index.html"; do
  [[ -f "$required" ]] || {
    echo "ERROR: staged release is incomplete: ${required}" >&2
    exit 1
  }
done
grep -Fxq "RELEASE_ID=${release_id}" "$release_dir/release.env" || {
  echo "ERROR: release manifest identity mismatch" >&2
  exit 1
}

mkdir -p "$shared_dir" "$state_dir/env-snapshots" "$backup_dir"
if ! mkdir "$lock_dir" 2>/dev/null; then
  echo "ERROR: another release operation holds ${lock_dir}" >&2
  exit 1
fi

runtime="${RELEASE_RUNTIME:-$release_dir/deploy/scripts/release-runtime.sh}"
previous_release=""
environment_snapshot_ready=false
state_pending_written=false
release_work_begun=false
runtime_requires_protection=false
deployment_committed=false
maintenance_was_enabled=false
[[ -f "$maintenance_file" ]] && maintenance_was_enabled=true

on_exit() {
  local status=$?
  local automatic_attempted=false
  local automatic_succeeded=false
  local environment_restored=false
  trap - EXIT

  if [[ -f "$active_file" && ! -L "$active_file" && ! -e "$pending_file" ]] \
    && [[ "$(cat "$active_file")" == "$release_id" ]]; then
    deployment_committed=true
  fi

  if [[ "$status" -ne 0 \
    && "$environment_snapshot_ready" == true \
    && "$deployment_committed" == false ]]; then
    if [[ "$release_work_begun" == true && -n "$previous_release" ]]; then
      automatic_attempted=true
      echo "ERROR: release ${release_id} failed; restoring ${previous_release}" >&2
      if DEPLOY_ROOT="$deploy_root" DATA_DIR="$data_dir" BACKUP_DIR="$backup_dir" \
        MYSQL_ENV="$mysql_env" RELEASE_RUNTIME="$runtime" \
        ROLLBACK_LOCK_HELD=true \
        bash "$release_dir/deploy/scripts/rollback.sh" \
          --from "$release_id" --to "$previous_release"; then
        automatic_succeeded=true
        environment_restored=true
      else
        echo "ERROR: automatic rollback failed; maintenance remains enabled" >&2
      fi
    fi

    if [[ "$automatic_succeeded" == false ]]; then
      if restore_bound_environment_snapshot \
        "$snapshot_file" "$snapshot_metadata_file" "$env_file" \
        "$release_id" "$previous_release"; then
        environment_restored=true
      else
        echo "ERROR: failed to restore the environment snapshot" >&2
      fi

      if [[ "$environment_restored" == true \
        && "$runtime_requires_protection" == false \
        && "$automatic_attempted" == false ]]; then
        if [[ "$state_pending_written" == true ]]; then
          if atomic_state_remove "$pending_file"; then
            state_pending_written=false
          else
            echo "ERROR: failed to clear pending release state" >&2
          fi
        fi
        if [[ "$maintenance_was_enabled" == true ]]; then
          atomic_enable_maintenance "$maintenance_file" \
            || echo "ERROR: failed to preserve maintenance state" >&2
        else
          atomic_state_remove "$maintenance_file" \
            || echo "ERROR: failed to preserve maintenance state" >&2
        fi
      else
        atomic_enable_maintenance "$maintenance_file" \
          || echo "ERROR: failed to enable maintenance after release failure" >&2
      fi
    fi
  fi

  rmdir "$lock_dir" 2>/dev/null || true
  exit "$status"
}
trap on_exit EXIT

read_root_password() {
  grep -E '^MYSQL_ROOT_PASSWORD=' "$mysql_env" | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

create_initial_environment() {
  local root_password
  local encoded_password
  local jwt_secret
  local redis_password
  local admin_password
  local temporary="${env_file}.initial.$$"
  local credentials_file="$state_dir/initial-admin-credentials"

  root_password="$(read_root_password)"
  [[ -n "$root_password" ]] || {
    echo "ERROR: MYSQL_ROOT_PASSWORD is unavailable" >&2
    return 1
  }
  encoded_password="$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$root_password")"
  jwt_secret="$(openssl rand -hex 32)"
  redis_password="$(openssl rand -hex 32)"
  admin_password="$(openssl rand -hex 12)"
  umask 077
  cat > "$temporary" <<ENV
DB_URL=mysql+aiomysql://root:${encoded_password}@mysql:3306/design_hub
REDIS_PASSWORD=${redis_password}
REDIS_URL=redis://:${redis_password}@redis:6379/0
PROVIDER_STANDARD_CONCURRENCY=3
PROVIDER_4K_CONCURRENCY=1
WORKER_READ_COUNT=8
WORKER_SHUTDOWN_TIMEOUT_SECONDS=30
IMAGE_OUTPUT_DIR=/app/generated
ASSET_OUTPUT_DIR=/app/assets
EXPORT_OUTPUT_DIR=/app/exports
JWT_SECRET=${jwt_secret}
JWT_TTL_HOURS=24
SEED_ADMIN_EMAIL=admin@design-hub.cn
SEED_ADMIN_PASSWORD=${admin_password}
SENTRY_DSN=
ENV
  chmod 600 "$temporary"
  mv "$temporary" "$env_file"
  cat > "$credentials_file" <<ENV
SEED_ADMIN_EMAIL=admin@design-hub.cn
SEED_ADMIN_PASSWORD=${admin_password}
ENV
  chmod 600 "$credentials_file"
  echo "    Initial administrator credentials: ${credentials_file}"
  unset root_password encoded_password jwt_secret redis_password admin_password
}

ensure_internal_redis_env() {
  local redis_password
  local expected_url
  local current_url
  [[ "$(grep -c '^REDIS_PASSWORD=' "$env_file" || true)" -le 1 ]]
  [[ "$(grep -c '^REDIS_URL=' "$env_file" || true)" -le 1 ]]
  if grep -q '^REDIS_PASSWORD=' "$env_file"; then
    redis_password="$(grep -E '^REDIS_PASSWORD=' "$env_file" | cut -d= -f2-)"
    [[ "$redis_password" =~ ^[0-9a-f]{64}$ ]] || {
      echo "ERROR: REDIS_PASSWORD must be 64 lowercase hexadecimal characters" >&2
      return 1
    }
  else
    redis_password="$(openssl rand -hex 32)"
    printf 'REDIS_PASSWORD=%s\n' "$redis_password" >> "$env_file"
  fi
  expected_url="redis://:${redis_password}@redis:6379/0"
  if grep -q '^REDIS_URL=' "$env_file"; then
    current_url="$(grep -E '^REDIS_URL=' "$env_file" | cut -d= -f2-)"
    [[ "$current_url" == "$expected_url" ]] || {
      echo "ERROR: REDIS_URL does not match the internal Redis service" >&2
      return 1
    }
  else
    printf 'REDIS_URL=%s\n' "$expected_url" >> "$env_file"
  fi
  unset redis_password expected_url current_url
}

validate_release_directory() {
  local target_release="$1"
  local target_dir="$deploy_root/releases/$target_release"
  [[ -f "$target_dir/release.env" \
    && -f "$target_dir/deploy/compose.yml" \
    && -f "$target_dir/web/index.html" ]] || {
    echo "ERROR: recorded release ${target_release} is incomplete" >&2
    return 1
  }
  grep -Fxq "RELEASE_ID=${target_release}" "$target_dir/release.env" || {
    echo "ERROR: recorded release manifest identity mismatch" >&2
    return 1
  }
}

import_legacy_release() {
  local legacy_id
  local incoming
  local target
  local legacy_hash

  [[ -z "$release_state_active" ]] || return 0
  [[ -f "$deploy_root/web/index.html" ]] || return 0
  legacy_id="legacy-$(date -u +%Y%m%dT%H%M%SZ)"
  incoming="$deploy_root/.incoming/$legacy_id"
  target="$deploy_root/releases/$legacy_id"
  [[ ! -e "$incoming" && ! -e "$target" ]]
  mkdir -p "$incoming/app" "$incoming/web" "$deploy_root/releases"
  cp -a "$release_dir/deploy" "$incoming/deploy"
  cp -a "$deploy_root/web/." "$incoming/web/"
  legacy_hash="$(sha256sum "$incoming/web/index.html" | cut -d' ' -f1)"
  cat > "$incoming/release.env" <<ENV
RELEASE_ID=${legacy_id}
SOURCE_COMMIT=legacy-import
WEB_INDEX_SHA256=${legacy_hash}
ENV
  mv "$incoming" "$target"
  bash "$runtime" import-legacy "$target" "$legacy_id"
  atomic_state_write "$active_file" "$legacy_id"
  release_state_active="$legacy_id"
  echo "    Imported rollback release: ${legacy_id}"
}

load_release_state "$active_file" "$previous_file" "$pending_file"
[[ -z "$release_state_pending" ]] || {
  echo "ERROR: pending release ${release_state_pending} requires recovery" >&2
  exit 1
}
if [[ -n "$release_state_active" ]]; then
  validate_release_directory "$release_state_active"
  resolve_release_rollback_target \
    "$state_dir" "$deploy_root/releases/$release_state_active" "$release_state_active"
  [[ "$release_state_previous" == "$release_rollback_target" ]] || {
    echo "ERROR: active, previous, and snapshot release state is inconsistent" >&2
    exit 1
  }
fi

if [[ ! -f "$env_file" ]]; then
  if [[ -f "$deploy_root/.env" ]]; then
    umask 077
    cp "$deploy_root/.env" "$env_file"
    chmod 600 "$env_file"
  else
    create_initial_environment
  fi
fi

import_legacy_release
previous_release="$release_state_active"
if [[ "$previous_release" == "$release_id" ]]; then
  echo "ERROR: release ${release_id} is already active" >&2
  exit 1
fi

# shellcheck source=mail-env.sh
ENV_FILE="$env_file"
export ENV_FILE
source "$release_dir/deploy/scripts/mail-env.sh"
chmod 600 "$env_file"
create_bound_environment_snapshot \
  "$env_file" "$snapshot_file" "$snapshot_metadata_file" \
  "$release_id" "$previous_release"
environment_snapshot_ready=true
atomic_state_write "$pending_file" "$release_id"
state_pending_written=true

migrate_legacy_mail_env
ensure_internal_redis_env
ensure_mail_env
chmod 600 "$env_file"

release_work_begun=true
echo "==> [1/9] Preparing release infrastructure"
bash "$runtime" prepare "$release_dir" "$release_id"
echo "==> [2/9] Building immutable API image"
bash "$runtime" build-release "$release_dir" "$release_id"

echo "==> [3/9] Enabling maintenance protection"
runtime_requires_protection=true
atomic_enable_maintenance "$maintenance_file"
bash "$runtime" enable-maintenance "$release_dir" "$release_id"
echo "==> [4/9] Backing up the database"
bash "$runtime" backup-database "$release_dir" "$release_id"
echo "==> [5/9] Applying migrations with the candidate image"
bash "$runtime" migrate "$release_dir" "$release_id"
echo "==> [6/9] Starting and checking the candidate API and worker"
bash "$runtime" start-release "$release_dir" "$release_id"
bash "$runtime" health-candidate "$release_dir" "$release_id"

echo "==> [7/9] Switching the web mount while the target remains active in state"
bash "$runtime" switch-web "$release_dir" "$release_id"
bash "$runtime" health-live "$release_dir" "$release_id"

echo "==> [8/9] Opening traffic and checking the public endpoint"
atomic_state_remove "$maintenance_file"
bash "$runtime" health-public "$release_dir" "$release_id"

echo "==> [9/9] Atomically committing release state"
if [[ -n "$previous_release" ]]; then
  atomic_state_write "$previous_file" "$previous_release"
else
  atomic_state_remove "$previous_file"
fi
atomic_promote_pending_release "$pending_file" "$active_file" "$release_id"
state_pending_written=false
deployment_committed=true
environment_snapshot_ready=false
echo "==> DEPLOY_DONE=${release_id}"
