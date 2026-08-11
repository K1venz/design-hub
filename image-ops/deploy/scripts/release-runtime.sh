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
server_ip="${SERVER_IP:-14.103.51.191}"
shared_dir="$deploy_root/shared"
state_dir="$deploy_root/state"
env_file="$shared_dir/.env"
compose_file="$release_dir/deploy/compose.yml"

[[ "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]
[[ -f "$compose_file" ]]

export RELEASE_ID="$release_id"
export DESIGN_HUB_RELEASE_DIR="$release_dir"
export DESIGN_HUB_SHARED_DIR="$shared_dir"
export DESIGN_HUB_STATE_DIR="$state_dir"
export DESIGN_HUB_DATA_DIR="$data_dir"
export DESIGN_HUB_ENV_FILE="$env_file"

compose() {
  docker compose --env-file "$env_file" -f "$compose_file" \
    --project-directory "$release_dir/deploy" "$@"
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
    "smtp.image.sepaitech.com A 14.103.51.191",
    'image.sepaitech.com TXT "v=spf1 ip4:14.103.51.191 -all"',
    f'designhub._domainkey.image.sepaitech.com TXT "{dkim}"',
    '_dmarc.image.sepaitech.com TXT "v=DMARC1; p=none"',
    "14.103.51.191 PTR smtp.image.sepaitech.com",
]
Path(sys.argv[2]).write_text("\n".join(records) + "\n")
PY
  chmod 600 "$dns_records"
}

case "$action" in
  import-legacy)
    image_repository="${API_IMAGE_REPOSITORY:-design-hub-api}"
    docker image inspect "${image_repository}:latest" >/dev/null
    docker image inspect "${image_repository}:${release_id}" >/dev/null 2>&1 && {
      echo "ERROR: imported legacy image identity already exists" >&2
      exit 1
    }
    docker image tag "${image_repository}:latest" "${image_repository}:${release_id}"
    unset image_repository
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
    image="${API_IMAGE_REPOSITORY:-design-hub-api}:${release_id}"
    if docker image inspect "$image" >/dev/null 2>&1; then
      echo "ERROR: immutable API image already exists: ${image}" >&2
      exit 1
    fi
    compose build api dkim smtp
    ensure_dkim_key
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
    compose run --rm --no-deps api alembic upgrade head
    ;;

  start-release)
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
