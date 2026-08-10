#!/usr/bin/env bash
set -euo pipefail

release_id="${1:?usage: deploy.sh RELEASE_ID}"
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
maintenance_file="$state_dir/maintenance"
snapshot_file="$state_dir/env-snapshots/$release_id.before.env"
lock_dir="$state_dir/deploy.lock"

if [[ ! "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "ERROR: invalid release identifier" >&2
  exit 1
fi
for required in "$release_dir/release.env" "$release_dir/deploy/compose.yml" \
  "$release_dir/deploy/scripts/mail-env.sh" "$release_dir/web/index.html"; do
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
rollback_armed=false

atomic_state_write() {
  local destination="$1"
  local value="$2"
  local temporary="${destination}.tmp.$$"
  printf '%s\n' "$value" > "$temporary"
  mv -f "$temporary" "$destination"
}

on_exit() {
  local status=$?
  trap - EXIT
  if [[ "$status" -ne 0 && "$rollback_armed" == true && -n "$previous_release" ]]; then
    echo "ERROR: release ${release_id} failed; restoring ${previous_release}" >&2
    if ! DEPLOY_ROOT="$deploy_root" DATA_DIR="$data_dir" BACKUP_DIR="$backup_dir" \
      MYSQL_ENV="$mysql_env" RELEASE_RUNTIME="$runtime" \
      ROLLBACK_LOCK_HELD=true \
      bash "$release_dir/deploy/scripts/rollback.sh" \
        --from "$release_id" --to "$previous_release" --env-snapshot "$snapshot_file"; then
      echo "ERROR: automatic rollback failed; maintenance remains enabled" >&2
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

import_legacy_release() {
  local legacy_id
  local incoming
  local target
  local legacy_hash

  [[ ! -f "$active_file" ]] || return 0
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
  echo "    Imported rollback release: ${legacy_id}"
}

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
if [[ -f "$active_file" ]]; then
  previous_release="$(cat "$active_file")"
fi
if [[ "$previous_release" == "$release_id" ]]; then
  echo "ERROR: release ${release_id} is already active" >&2
  exit 1
fi

# shellcheck source=mail-env.sh
ENV_FILE="$env_file"
export ENV_FILE
source "$release_dir/deploy/scripts/mail-env.sh"
[[ ! -e "$snapshot_file" ]] || {
  echo "ERROR: environment snapshot already exists for immutable release ${release_id}" >&2
  exit 1
}
snapshot_environment "$env_file" "$snapshot_file"
migrate_legacy_mail_env
ensure_internal_redis_env
ensure_mail_env
chmod 600 "$env_file"
rollback_armed=true

echo "==> [1/9] Preparing release infrastructure"
bash "$runtime" prepare "$release_dir" "$release_id"
echo "==> [2/9] Building immutable API image"
bash "$runtime" build-release "$release_dir" "$release_id"

echo "==> [3/9] Enabling maintenance protection"
touch "$maintenance_file"
bash "$runtime" enable-maintenance "$release_dir" "$release_id"
echo "==> [4/9] Backing up the database"
bash "$runtime" backup-database "$release_dir" "$release_id"
echo "==> [5/9] Applying migrations with the candidate image"
bash "$runtime" migrate "$release_dir" "$release_id"
echo "==> [6/9] Starting and checking the candidate API and worker"
bash "$runtime" start-release "$release_dir" "$release_id"
bash "$runtime" health-candidate "$release_dir" "$release_id"

echo "==> [7/9] Atomically selecting the release and switching the web mount"
atomic_state_write "$active_file" "$release_id"
bash "$runtime" switch-web "$release_dir" "$release_id"
bash "$runtime" health-live "$release_dir" "$release_id"

echo "==> [8/9] Opening traffic and checking the public endpoint"
rm -f "$maintenance_file"
bash "$runtime" health-public "$release_dir" "$release_id"

echo "==> [9/9] Recording rollback identity"
if [[ -n "$previous_release" ]]; then
  atomic_state_write "$previous_file" "$previous_release"
fi
rollback_armed=false
echo "==> DEPLOY_DONE=${release_id}"
