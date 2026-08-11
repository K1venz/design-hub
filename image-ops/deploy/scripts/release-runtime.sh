#!/usr/bin/env bash
set -euo pipefail

action="${1:?runtime action is required}"
release_dir="${2:?release directory is required}"
release_id="${3:?release identifier is required}"
argument="${4:-}"

deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
data_dir="${DATA_DIR:-/data/docker/design-hub}"
backup_dir="${BACKUP_DIR:-/root}"
mysql_env="${MYSQL_ENV:-/opt/docker/mysql/.env}"
server_ip="${SERVER_IP:-203.0.113.10}"
shared_dir="$deploy_root/shared"
state_dir="$deploy_root/state"
env_file="$shared_dir/.env"
compose_file="$release_dir/deploy/compose.yml"

[[ "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]
[[ -f "$compose_file" ]]
[[ "$(grep -c '^SOURCE_COMMIT=' "$release_dir/release.env" || true)" -eq 1 ]]
SOURCE_COMMIT="$(sed -n 's/^SOURCE_COMMIT=//p' "$release_dir/release.env")"
[[ "$SOURCE_COMMIT" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]]

export RELEASE_ID="$release_id"
export DESIGN_HUB_RELEASE_DIR="$release_dir"
export DESIGN_HUB_SHARED_DIR="$shared_dir"
export DESIGN_HUB_STATE_DIR="$state_dir"
export DESIGN_HUB_DATA_DIR="$data_dir"
export DESIGN_HUB_ENV_FILE="$env_file"
export SOURCE_COMMIT

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" \
    --project-directory "$release_dir/deploy" "$@"
}

load_manifest_value() {
  local key="$1" count
  count="$(grep -c "^${key}=" "$release_dir/release.env" || true)"
  [[ "$count" -eq 1 ]] || { echo "ERROR: release manifest field ${key} is malformed" >&2; return 1; }
  manifest_value="$(sed -n "s/^${key}=//p" "$release_dir/release.env")"
  [[ -n "$manifest_value" && "$manifest_value" != *$'\n'* ]] || return 1
}

write_api_image_identity() {
  local destination="$1" repository="$2" source_commit="$3" image_id="$4" temporary
  mkdir -p "$(dirname "$destination")"
  temporary="$(mktemp "$(dirname "$destination")/.api-image.XXXXXX")" || return 1
  umask 077
  if ! printf '%s\n' 'API_IMAGE_IDENTITY_FORMAT=1' "REPOSITORY=$repository" \
    "RELEASE_ID=$release_id" "SOURCE_COMMIT=$source_commit" "IMAGE_ID=$image_id" > "$temporary" \
    || ! chmod 600 "$temporary" || ! mv -f "$temporary" "$destination"; then
    rm -f "$temporary"; return 1
  fi
}

verify_api_image_identity() {
  local identity_file="$1" repository="$2" source_commit="$3" actual_image_id="$4"
  [[ -f "$identity_file" && ! -L "$identity_file" && "$(stat -c '%a' "$identity_file")" == 600 \
    && "$(wc -l < "$identity_file")" -eq 5 ]] || return 1
  grep -Fxq 'API_IMAGE_IDENTITY_FORMAT=1' "$identity_file" \
    && grep -Fxq "REPOSITORY=$repository" "$identity_file" \
    && grep -Fxq "RELEASE_ID=$release_id" "$identity_file" \
    && grep -Fxq "SOURCE_COMMIT=$source_commit" "$identity_file" \
    && grep -Fxq "IMAGE_ID=$actual_image_id" "$identity_file"
}

inspect_api_image_object() {
  local image="$1" tuple
  tuple="$(docker image inspect --format '{{printf "%s\t%s\t%s\t%s" .Id (index .Config.Labels "cn.design-hub.release-id") (index .Config.Labels "cn.design-hub.source-commit") (index .Config.Labels "cn.design-hub.image-repository")}}' "$image")" || return 1
  IFS=$'\t' read -r inspected_image_id inspected_release inspected_source inspected_repository <<< "$tuple"
  [[ "$inspected_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || return 1
}

verify_inspected_api_image() {
  local repository="$1" source_commit="$2"
  [[ "$inspected_release" == "$release_id" \
    && "$inspected_source" == "$source_commit" \
    && "$inspected_repository" == "$repository" ]]
}

load_api_image_reference() {
  local repository="${API_IMAGE_REPOSITORY:-design-hub-api}" identity_file="$state_dir/image-identities/${release_id}.api" image_id
  load_manifest_value SOURCE_COMMIT
  image_id="$(sed -n 's/^IMAGE_ID=//p' "$identity_file" 2>/dev/null || true)"
  [[ "$image_id" =~ ^sha256:[0-9a-f]{64}$ ]] \
    || { echo "ERROR: immutable API image identity is unavailable" >&2; return 1; }
  verify_api_image_identity "$identity_file" "$repository" "$manifest_value" "$image_id" \
    || { echo "ERROR: immutable API image identity does not match the release manifest" >&2; return 1; }
  docker image inspect "$image_id" >/dev/null \
    || { echo "ERROR: immutable API image object is unavailable" >&2; return 1; }
  API_IMAGE_REFERENCE="$image_id"
  export API_IMAGE_REFERENCE
}

read_protected_image_id_file() {
  local path="$1"
  [[ -f "$path" && ! -L "$path" && "$(stat -c '%a' "$path")" == 600 \
    && "$(wc -l < "$path")" -eq 1 ]] || return 1
  protected_image_id="$(cat "$path")"
  [[ "$protected_image_id" =~ ^sha256:[0-9a-f]{64}$ ]]
}

read_root_password() {
  grep -E '^MYSQL_ROOT_PASSWORD=' "$mysql_env" | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

wait_healthy() {
  local container="$1"
  local label="$2"
  local status="unknown"
  for attempt in $(seq 1 40); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo unknown)"
    echo "    ${label} health: ${status} (${attempt})"
    [[ "$status" == healthy ]] && return 0
    if [[ "$status" == unhealthy ]]; then
      docker logs --tail 60 "$container"
      return 1
    fi
    sleep 5
  done
  echo "ERROR: ${label} health check timed out with status ${status}" >&2
  docker logs --tail 60 "$container"
  return 1
}

ensure_dkim_key() {
  local key_dir="$data_dir/mail/dkim"
  local private_key="$key_dir/designhub.private"
  local public_record="$key_dir/designhub.txt"
  local dns_records="$data_dir/mail/dns-records.txt"

  if [[ -e "$private_key" || -e "$public_record" ]]; then
    [[ -s "$private_key" && -s "$public_record" ]] || {
      echo "ERROR: incomplete DKIM key pair" >&2
      return 1
    }
  else
    compose run --rm --no-deps --entrypoint opendkim-genkey dkim \
      -b 2048 -d image.sepaitech.com -D /etc/dkimkeys -s designhub
  fi
  chmod 600 "$private_key" "$public_record"
  python3 - "$public_record" "$dns_records" <<'PY'
from pathlib import Path
import re
import sys

source = Path(sys.argv[1]).read_text()
parts = re.findall(r'"([^"]*)"', source)
if not parts:
    raise SystemExit("unable to parse generated DKIM record")
dkim = "".join(parts)
records = [
    "smtp.image.sepaitech.com A 203.0.113.10",
    'image.sepaitech.com TXT "v=spf1 ip4:203.0.113.10 -all"',
    f'designhub._domainkey.image.sepaitech.com TXT "{dkim}"',
    '_dmarc.image.sepaitech.com TXT "v=DMARC1; p=none"',
    "203.0.113.10 PTR smtp.image.sepaitech.com",
]
Path(sys.argv[2]).write_text("\n".join(records) + "\n")
PY
  chmod 600 "$dns_records"
}

case "$action" in
  import-legacy)
    image_repository="${API_IMAGE_REPOSITORY:-design-hub-api}"
    identity_file="$state_dir/image-identities/${release_id}.api"
    import_identity_file="${identity_file}.importing"
    mkdir -p "$(dirname "$identity_file")"
    source_image_id="$(docker image inspect --format '{{.Id}}' "${image_repository}:latest")"
    [[ "$source_image_id" =~ ^sha256:[0-9a-f]{64}$ ]] || { echo "ERROR: legacy source image has an invalid immutable ID" >&2; exit 1; }
    if [[ ! -e "$import_identity_file" && ! -L "$import_identity_file" ]]; then
      umask 077
      printf '%s\n' "$source_image_id" > "$import_identity_file"
      chmod 600 "$import_identity_file"
    fi
    read_protected_image_id_file "$import_identity_file" \
      || { echo "ERROR: legacy import identity is invalid" >&2; exit 1; }
    [[ "$protected_image_id" == "$source_image_id" ]] \
      || { echo "ERROR: legacy source tag changed during import" >&2; exit 1; }
    if ! docker image inspect "${image_repository}:${release_id}" >/dev/null 2>&1; then
      docker image tag "${image_repository}:latest" "${image_repository}:${release_id}"
    fi
    image_id="$(docker image inspect --format '{{.Id}}' "${image_repository}:${release_id}")"
    [[ "$image_id" == "$protected_image_id" ]] || { echo "ERROR: imported legacy tag differs from its immutable source" >&2; exit 1; }
    if [[ -e "$identity_file" || -L "$identity_file" ]]; then
      verify_api_image_identity "$identity_file" "$image_repository" "$SOURCE_COMMIT" "$image_id" \
        || { echo "ERROR: imported legacy image identity conflicts with the manifest" >&2; exit 1; }
    else
      write_api_image_identity "$identity_file" "$image_repository" "$SOURCE_COMMIT" "$image_id"
    fi
    rm -- "$import_identity_file"
    unset image_repository identity_file import_identity_file source_image_id image_id protected_image_id
    ;;

  prepare)
    mkdir -p "$data_dir"/{generated,assets,exports,redis} "$data_dir/mail"/{spool,dkim}
    mkdir -p "$shared_dir/nginx/certs" "$state_dir" "$backup_dir"
    chmod 700 "$data_dir/mail/dkim"
    if [[ ! -f "$shared_dir/nginx/certs/design-hub.crt" ]]; then
      openssl req -x509 -nodes -newkey rsa:2048 \
        -keyout "$shared_dir/nginx/certs/design-hub.key" \
        -out "$shared_dir/nginx/certs/design-hub.crt" \
        -days 825 -subj "/C=CN/O=design-hub/CN=design-hub.local" \
        -addext "subjectAltName=IP:${server_ip},DNS:design-hub.local" 2>/dev/null
    fi
    config_json="$(compose config --format json)"
    COMPOSE_CONFIG_JSON="$config_json" bash "$release_dir/deploy/scripts/check-mail-config.sh"
    bash "$release_dir/deploy/scripts/test-mail-env.sh"
    root_password="$(read_root_password)"
    [[ -n "$root_password" ]]
    docker exec -i -e MYSQL_PWD="$root_password" mysql mysql -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS `design_hub` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL
    unset root_password config_json
    ;;

  build-release)
    image_repository="${API_IMAGE_REPOSITORY:-design-hub-api}"
    [[ "$image_repository" =~ ^[A-Za-z0-9][A-Za-z0-9._/:_-]*$ ]] \
      || { echo "ERROR: API image repository is invalid" >&2; exit 1; }
    image="${image_repository}:${release_id}"
    identity_file="$state_dir/image-identities/${release_id}.api"
    build_identity_file="${identity_file}.building"
    load_manifest_value SOURCE_COMMIT
    source_commit="$manifest_value"
    if docker image inspect "$image" >/dev/null 2>&1; then
      inspect_api_image_object "$image" \
        || { echo "ERROR: existing API image object is invalid" >&2; exit 1; }
      image_id="$inspected_image_id"
      verify_inspected_api_image "$image_repository" "$source_commit" \
        || { echo "ERROR: existing API image labels do not match this release manifest" >&2; exit 1; }
      if [[ -e "$identity_file" || -L "$identity_file" ]]; then
        verify_api_image_identity "$identity_file" "$image_repository" "$source_commit" "$image_id" \
          || { echo "ERROR: existing API image is not bound to this release manifest" >&2; exit 1; }
      else
        read_protected_image_id_file "$build_identity_file" \
          || { echo "ERROR: existing API image has no protected build identity" >&2; exit 1; }
        [[ "$protected_image_id" == "$image_id" ]] \
          || { echo "ERROR: existing API image differs from its protected build identity" >&2; exit 1; }
        write_api_image_identity "$identity_file" "$image_repository" "$source_commit" "$image_id"
        rm -- "$build_identity_file"
      fi
      echo "    Reusing manifest-bound immutable API image: ${image}"
    else
      [[ ! -e "$identity_file" && ! -L "$identity_file" \
        && ! -e "$build_identity_file" && ! -L "$build_identity_file" ]] \
        || { echo "ERROR: API image identity exists without its immutable image" >&2; exit 1; }
      mkdir -p "$(dirname "$identity_file")"
      umask 077
      docker build --iidfile "$build_identity_file" \
        --file "$release_dir/deploy/app/Dockerfile" \
        --label "cn.design-hub.release-id=$release_id" \
        --label "cn.design-hub.source-commit=$source_commit" \
        --label "cn.design-hub.image-repository=$image_repository" \
        --tag "$image" "$release_dir/app"
      chmod 600 "$build_identity_file"
      read_protected_image_id_file "$build_identity_file" \
        || { echo "ERROR: Docker did not produce a protected immutable image ID" >&2; exit 1; }
      image_id="$protected_image_id"
      compose build dkim smtp
      inspect_api_image_object "$image" \
        || { echo "ERROR: built API image object is invalid" >&2; exit 1; }
      [[ "$inspected_image_id" == "$image_id" ]] \
        || { echo "ERROR: API image tag changed after its immutable build" >&2; exit 1; }
      verify_inspected_api_image "$image_repository" "$source_commit" \
        || { echo "ERROR: built API image labels do not match this release manifest" >&2; exit 1; }
      write_api_image_identity "$identity_file" "$image_repository" "$source_commit" "$image_id"
      rm -- "$build_identity_file"
    fi
    ensure_dkim_key
    unset image_repository image identity_file build_identity_file source_commit image_id manifest_value protected_image_id
    ;;

  enable-maintenance)
    compose up -d --no-deps --force-recreate nginx
    docker exec design-hub-nginx nginx -t
    ;;

  backup-database)
    mkdir -p "$backup_dir"
    backup_path="$backup_dir/db-backup-${release_id}-$(date -u +%Y%m%dT%H%M%SZ).sql"
    root_password="$(read_root_password)"
    if docker exec -e MYSQL_PWD="$root_password" mysql mysqldump -uroot \
      --no-tablespaces --single-transaction --routines design_hub \
      > "$backup_path" 2>/dev/null && [[ -s "$backup_path" ]]; then
      chmod 600 "$backup_path"
      echo "    Database backup: ${backup_path}"
    else
      echo "ERROR: database backup failed" >&2
      exit 1
    fi
    unset root_password
    ;;

  migrate)
    load_api_image_reference
    compose run --rm --no-deps api alembic upgrade head
    ;;

  start-release)
    load_api_image_reference
    compose up -d redis dkim smtp
    wait_healthy design-hub-redis redis
    wait_healthy design-hub-dkim dkim
    wait_healthy design-hub-smtp smtp
    compose up -d api worker
    wait_healthy design-hub-api api
    wait_healthy design-hub-worker worker
    ;;

  health-candidate)
    docker exec design-hub-api python -c \
      "import urllib.request; assert urllib.request.urlopen('http://localhost:8000/metrics', timeout=3).status == 200"
    docker exec design-hub-api alembic current
    ;;

  switch-web)
    compose up -d --no-deps --force-recreate nginx
    ;;

  health-live)
    docker exec design-hub-nginx nginx -t
    docker exec design-hub-nginx test -s /usr/share/nginx/html/index.html
    expected_hash="$(grep -E '^WEB_INDEX_SHA256=' "$release_dir/release.env" | cut -d= -f2-)"
    actual_hash="$(docker exec design-hub-nginx sha256sum /usr/share/nginx/html/index.html | cut -d' ' -f1)"
    [[ -n "$expected_hash" && "$actual_hash" == "$expected_hash" ]]
    ;;

  health-public)
    connect_timeout="${PUBLIC_HEALTH_CONNECT_TIMEOUT_SECONDS:-3}"
    max_timeout="${PUBLIC_HEALTH_MAX_TIMEOUT_SECONDS:-10}"
    [[ "$connect_timeout" =~ ^[1-9][0-9]*$ && "$connect_timeout" -le 30 ]]
    [[ "$max_timeout" =~ ^[1-9][0-9]*$ && "$max_timeout" -le 120 ]]
    curl --fail --silent --show-error --insecure \
      --connect-timeout "$connect_timeout" --max-time "$max_timeout" \
      "${PUBLIC_HEALTH_URL:-https://127.0.0.1/}" >/dev/null
    ;;

  stop-application)
    compose stop api worker
    ;;

  verify-application-stopped)
    for container in design-hub-api design-hub-worker; do
      inspect_error="$(mktemp)"
      if docker container inspect "$container" >/dev/null 2>"$inspect_error"; then
        running="$(docker inspect -f '{{.State.Running}}' "$container")"
        [[ "$running" == false ]] || {
          echo "ERROR: ${container} is still running before schema restore" >&2
          rm -f "$inspect_error"
          exit 1
        }
      elif grep -Fq "No such container: $container" "$inspect_error"; then
        :
      else
        echo "ERROR: unable to inspect ${container} before schema restore" >&2
        cat "$inspect_error" >&2
        rm -f "$inspect_error"
        exit 1
      fi
      rm -f "$inspect_error"
    done
    unset container running inspect_error
    ;;

  verify-application-owned)
    for container in design-hub-api design-hub-worker; do
      inspect_error="$(mktemp)"
      if owner_release="$(docker container inspect --format '{{ index .Config.Labels "com.design-hub.release" }}' "$container" 2>"$inspect_error")"; then
        [[ "$owner_release" == "$release_id" ]] || {
          echo "ERROR: ${container} belongs to another release" >&2
          rm -f "$inspect_error"
          exit 1
        }
      elif grep -Fqx "Error: No such container: $container" "$inspect_error"; then
        :
      else
        echo "ERROR: unable to inspect ${container} ownership" >&2
        cat "$inspect_error" >&2
        rm -f "$inspect_error"
        exit 1
      fi
      rm -f "$inspect_error"
    done
    unset container owner_release inspect_error
    ;;

  restore-schema)
    root_password="$(read_root_password)"
    docker exec -i -e MYSQL_PWD="$root_password" mysql mysql -uroot design_hub
    unset root_password
    ;;

  *)
    echo "ERROR: unknown release runtime action: ${action}" >&2
    exit 2
    ;;
esac
