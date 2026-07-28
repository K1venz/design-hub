#!/usr/bin/env bash
# design-hub 部署编排（在服务器 203.0.113.10 上执行）。
# 复用现有 MySQL 8.4(/opt/docker/mysql)；首发 nginx+TLS(自签)；密钥不入库；幂等可重跑。
set -euo pipefail

DEPLOY_DIR="/opt/docker/design-hub"
DATA_DIR="/data/docker/design-hub"
MYSQL_ENV="/opt/docker/mysql/.env"
SERVER_IP="203.0.113.10"

cd "$DEPLOY_DIR"

read_root_pw() {
  # 从 mysql 容器配置读取 root 密码（去除可能的引号），不打印
  grep -E '^MYSQL_ROOT_PASSWORD=' "$MYSQL_ENV" | head -1 | cut -d= -f2- \
    | sed -e 's/^"//' -e 's/"$//' -e "s/^'//" -e "s/'\$//"
}

echo "==> [1/7] 持久化目录"
mkdir -p "$DATA_DIR"/generated "$DATA_DIR"/assets "$DATA_DIR"/exports
mkdir -p "$DEPLOY_DIR/nginx/certs"

echo "==> [2/7] 自签 TLS 证书"
if [[ ! -f nginx/certs/design-hub.crt ]]; then
  openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout nginx/certs/design-hub.key \
    -out    nginx/certs/design-hub.crt \
    -days 825 \
    -subj "/C=CN/O=design-hub/CN=design-hub.local" \
    -addext "subjectAltName=IP:${SERVER_IP},DNS:design-hub.local" 2>/dev/null
  echo "    自签证书已生成"
else
  echo "    已存在，跳过"
fi

echo "==> [3/7] 生成 .env（已存在则保留，不覆盖已有密钥）"
if [[ ! -f .env ]]; then
  ROOT_PW="$(read_root_pw)"
  [[ -n "$ROOT_PW" ]] || { echo "ERROR: 读不到 MYSQL_ROOT_PASSWORD"; exit 1; }
  ENC_PW="$(python3 -c 'import urllib.parse,sys;print(urllib.parse.quote(sys.argv[1],safe=""))' "$ROOT_PW")"
  JWT="$(openssl rand -hex 32)"
  ADMIN_PW="$(openssl rand -hex 12)"
  # 注意：勿用 .local 等保留域名——登录边界 EmailStr 会拒（422）
  ADMIN_EMAIL="admin@design-hub.cn"
  umask 077
  cat > .env <<ENV
DB_URL=mysql+aiomysql://root:${ENC_PW}@mysql:3306/design_hub
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
  echo "    .env 已生成（含本次生成的管理员凭据，仅打印一次）"
  echo "    __SEED_ADMIN_EMAIL__=${ADMIN_EMAIL}"
  echo "    __SEED_ADMIN_PASSWORD__=${ADMIN_PW}"
else
  echo "    .env 已存在，保留"
fi

if ! grep -Eq '^REDIS_URL=rediss?://[^[:space:]]+$' .env; then
  echo "ERROR: .env 缺少有效 REDIS_URL；必须先配置独立托管 Redis"; exit 1
fi
if grep -Eq '^REDIS_URL=rediss?://(127\.0\.0\.1|localhost)(:|/)' .env; then
  echo "ERROR: 生产 REDIS_URL 禁止指向当前 API 主机"; exit 1
fi

echo "==> [4/7] 建业务库 design_hub（utf8mb4，幂等）"
ROOT_PW="$(read_root_pw)"
docker exec -i -e MYSQL_PWD="$ROOT_PW" mysql mysql -uroot <<'SQL'
CREATE DATABASE IF NOT EXISTS `design_hub` CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
SQL
echo "    OK"

echo "==> [5/7] 构建镜像"
docker compose build

echo "==> [5a/7] Redis 连接预检（不输出连接凭据）"
docker compose run --rm --no-deps worker python -c \
  'import os; from redis import Redis; r=Redis.from_url(os.environ["REDIS_URL"],socket_connect_timeout=5,socket_timeout=5); assert r.ping() is True; r.close()'
echo "    OK"

echo "==> [6a/7] 迁移前全库备份（数据底线：破坏性迁移可回滚）"
BK="/root/db-backup-$(date +%Y%m%d-%H%M%S).sql"
if docker exec -e MYSQL_PWD="$ROOT_PW" mysql mysqldump -uroot --no-tablespaces \
     --single-transaction --routines design_hub > "$BK" 2>/dev/null && [[ -s "$BK" ]]; then
  echo "    备份 -> $BK ($(wc -c <"$BK") bytes)"
  # 滚动保留最近 10 份
  ls -t /root/db-backup-*.sql 2>/dev/null | tail -n +11 | xargs -r rm -f
else
  echo "    ERROR: 迁移前备份失败，中止部署（不带备份不迁移）"; exit 1
fi

echo "==> [6/7] 数据库迁移（建表，先于应用启动）"
docker compose run --rm --no-deps api alembic upgrade head

echo "==> [7/7] 启动 api + worker + nginx"
docker compose up -d

wait_healthy() {
  local container="$1"
  local label="$2"
  local st="unknown"
  for i in $(seq 1 40); do
    st="$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo unknown)"
    echo "    ${label} health: $st ($i)"
    [[ "$st" == "healthy" ]] && return 0
    if [[ "$st" == "unhealthy" ]]; then
      echo "ERROR: ${label} 不健康，输出最近日志"
      docker logs --tail 60 "$container"
      return 1
    fi
    sleep 5
  done
  echo "ERROR: ${label} 健康检查超时，最终状态=${st}"
  docker logs --tail 60 "$container"
  return 1
}

echo "==> 等待 API 与 Worker 健康检查..."
wait_healthy design-hub-api api
wait_healthy design-hub-worker worker

echo "==> 容器状态:"
docker compose ps
echo "==> DEPLOY_DONE"
