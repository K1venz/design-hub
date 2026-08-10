#!/usr/bin/env bash
set -euo pipefail

DEPLOY_DIR="/opt/docker/design-hub"
DATA_DIR="/data/docker/design-hub"
MYSQL_ENV="/opt/docker/mysql/.env"
SERVER_IP="14.103.51.191"

cd "$DEPLOY_DIR"

# shellcheck source=mail-env.sh
source scripts/mail-env.sh

read_root_pw() {
  grep -E '^MYSQL_ROOT_PASSWORD=' "$MYSQL_ENV" | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

wait_healthy() {
  local container="$1"
  local label="$2"
  local status="unknown"

  for attempt in $(seq 1 40); do
    status="$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo unknown)"
    echo "    ${label} health: ${status} (${attempt})"
    [[ "$status" == "healthy" ]] && return 0
    if [[ "$status" == "unhealthy" ]]; then
      docker logs --tail 60 "$container"
      return 1
    fi
    sleep 5
  done

  echo "ERROR: ${label} health check timed out with status ${status}" >&2
  docker logs --tail 60 "$container"
  return 1
}

ensure_internal_redis_env() {
  local redis_password
  local current_redis_url
  local expected_redis_url

  if [[ "$(grep -c '^REDIS_PASSWORD=' .env || true)" -gt 1 ]]; then
    echo "ERROR: duplicate REDIS_PASSWORD in .env" >&2
    return 1
  fi
  if [[ "$(grep -c '^REDIS_URL=' .env || true)" -gt 1 ]]; then
    echo "ERROR: duplicate REDIS_URL in .env" >&2
    return 1
  fi

  if grep -q '^REDIS_PASSWORD=' .env; then
    redis_password="$(grep -E '^REDIS_PASSWORD=' .env | cut -d= -f2-)"
    if [[ ! "$redis_password" =~ ^[0-9a-f]{64}$ ]]; then
      echo "ERROR: REDIS_PASSWORD must be 64 lowercase hexadecimal characters" >&2
      return 1
    fi
  else
    redis_password="$(openssl rand -hex 32)"
    printf '\nREDIS_PASSWORD=%s\n' "$redis_password" >> .env
  fi

  expected_redis_url="redis://:${redis_password}@redis:6379/0"
  if ! grep -q '^REDIS_URL=' .env; then
    printf 'REDIS_URL=%s\n' "$expected_redis_url" >> .env
  else
    current_redis_url="$(grep -E '^REDIS_URL=' .env | cut -d= -f2-)"
    if [[ -z "$current_redis_url" ]]; then
      sed -i "s#^REDIS_URL=.*#REDIS_URL=${expected_redis_url}#" .env
    elif [[ "$current_redis_url" != "$expected_redis_url" ]]; then
      echo "ERROR: REDIS_URL does not match the internal Redis service" >&2
      return 1
    fi
  fi

  unset redis_password current_redis_url expected_redis_url
  chmod 600 .env
}

ensure_dkim_key() {
  local key_dir="$DATA_DIR/mail/dkim"
  local private_key="$key_dir/designhub.private"
  local public_record="$key_dir/designhub.txt"
  local dns_records="$DATA_DIR/mail/dns-records.txt"

  if [[ -e "$private_key" || -e "$public_record" ]]; then
    if [[ ! -s "$private_key" || ! -s "$public_record" ]]; then
      echo "ERROR: incomplete DKIM key pair in ${key_dir}" >&2
      return 1
    fi
  else
    docker compose run --rm --no-deps --entrypoint opendkim-genkey dkim \
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

echo "==> [1/11] Preparing persistent directories"
mkdir -p "$DATA_DIR"/{generated,assets,exports,redis} "$DATA_DIR/mail"/{spool,dkim}
mkdir -p "$DEPLOY_DIR/nginx/certs"
chmod 700 "$DATA_DIR/mail/dkim"

echo "==> [2/11] Ensuring the local TLS certificate"
if [[ ! -f nginx/certs/design-hub.crt ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout nginx/certs/design-hub.key \
    -out nginx/certs/design-hub.crt \
    -days 825 \
    -subj "/C=CN/O=design-hub/CN=design-hub.local" \
    -addext "subjectAltName=IP:${SERVER_IP},DNS:design-hub.local" 2>/dev/null
fi

echo "==> [3/11] Ensuring application environment"
if [[ ! -f .env ]]; then
  ROOT_PW="$(read_root_pw)"
  [[ -n "$ROOT_PW" ]] || { echo "ERROR: MYSQL_ROOT_PASSWORD is unavailable" >&2; exit 1; }
  ENC_PW="$(python3 -c 'import urllib.parse,sys; print(urllib.parse.quote(sys.argv[1], safe=""))' "$ROOT_PW")"
  JWT="$(openssl rand -hex 32)"
  REDIS_PW="$(openssl rand -hex 32)"
  ADMIN_PW="$(openssl rand -hex 12)"
  ADMIN_EMAIL="admin@design-hub.cn"
  umask 077
  cat > .env <<ENV
DB_URL=mysql+aiomysql://root:${ENC_PW}@mysql:3306/design_hub
REDIS_PASSWORD=${REDIS_PW}
REDIS_URL=
PROVIDER_STANDARD_CONCURRENCY=3
PROVIDER_4K_CONCURRENCY=1
WORKER_READ_COUNT=8
WORKER_SHUTDOWN_TIMEOUT_SECONDS=30
IMAGE_OUTPUT_DIR=/app/generated
ASSET_OUTPUT_DIR=/app/assets
EXPORT_OUTPUT_DIR=/app/exports
JWT_SECRET=${JWT}
JWT_TTL_HOURS=24
SEED_ADMIN_EMAIL=${ADMIN_EMAIL}
SEED_ADMIN_PASSWORD=${ADMIN_PW}
GPT_IMAGE_BASE_URL=
GPT_IMAGE_API_KEY=
GPT_IMAGE_4K_API_KEY=
GPT_IMAGE_MODEL=
DASHSCOPE_KEY=
OPENAI_API_KEY=
SENTRY_DSN=
ENV
  echo "    __SEED_ADMIN_EMAIL__=${ADMIN_EMAIL}"
  echo "    __SEED_ADMIN_PASSWORD__=${ADMIN_PW}"
  unset REDIS_PW ADMIN_PW JWT ENC_PW
fi

ensure_internal_redis_env
ensure_mail_env
echo "    Redis and mail secrets are ready (values hidden)"

echo "==> [4/11] Validating mail configuration"
bash scripts/check-mail-config.sh
bash scripts/test-mail-env.sh

echo "==> [5/11] Ensuring the design_hub database"
ROOT_PW="$(read_root_pw)"
docker exec -i -e MYSQL_PWD="$ROOT_PW" mysql mysql -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS `design_hub` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL

echo "==> [6/11] Building application and mail images"
docker compose build
ensure_dkim_key

echo "==> [7/11] Starting and checking infrastructure"
docker compose up -d redis dkim smtp
wait_healthy design-hub-redis redis
wait_healthy design-hub-dkim dkim
wait_healthy design-hub-smtp smtp
docker compose run --rm --no-deps worker python -c \
  'import os; from redis import Redis; r=Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=5,socket_timeout=5); assert r.ping() is True; r.close()'
docker compose run --rm --no-deps api python -c \
  'import smtplib; client=smtplib.SMTP("smtp",25,timeout=5); code,_=client.noop(); assert code==250; client.quit()'

echo "==> [8/11] Backing up the database"
BK="/root/db-backup-$(date +%Y%m%d-%H%M%S).sql"
if docker exec -e MYSQL_PWD="$ROOT_PW" mysql mysqldump -uroot --no-tablespaces \
     --single-transaction --routines design_hub > "$BK" 2>/dev/null && [[ -s "$BK" ]]; then
  echo "    Backup: ${BK} ($(wc -c <"$BK") bytes)"
  ls -t /root/db-backup-*.sql 2>/dev/null | tail -n +11 | xargs -r rm -f
else
  echo "ERROR: database backup failed; refusing to migrate" >&2
  exit 1
fi

echo "==> [9/11] Applying database migrations"
docker compose run --rm --no-deps api alembic upgrade head

echo "==> [10/11] Starting the complete stack"
docker compose up -d
wait_healthy design-hub-api api
wait_healthy design-hub-worker worker

echo "==> [11/11] Validating and reloading nginx"
docker exec design-hub-nginx nginx -t
docker exec design-hub-nginx nginx -s reload

docker compose ps
echo "==> DNS_RECORDS_FILE=${DATA_DIR}/mail/dns-records.txt"
echo "==> DEPLOY_DONE"
