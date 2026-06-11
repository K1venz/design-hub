#!/usr/bin/env bash
# 本地执行：构建前端 + 把源码 + 部署产物 + 前端 dist 推到服务器。推完在服务器跑 deploy.sh 重建。
# 用法：bash image-ops/deploy/scripts/push.sh
# 可用环境变量覆盖：DEPLOY_KEY、DEPLOY_HOST
#
# 为何前端无条件重建：B-1② 去掉 CI auto-deploy(原本 npm build+ship dist)后，前端 build+部署=手动。
# 手搓 rsync 部署必漏前端(0040 demo 实锤：ship 了旧 bundle、/edit 路由不在)。故 push.sh 是唯一部署入口，
# 每次无条件重建 dist 杜绝 stale/漏建。需 node(版本见 image-web/.nvmrc)。
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # image-ops/deploy
REPO="$(cd "$HERE/../.." && pwd)"          # image-gen 仓库根
KEY="${DEPLOY_KEY:-$HOME/.ssh/dh_deploy_ed25519}"
HOST="${DEPLOY_HOST:-root@203.0.113.10}"
DEST="/opt/docker/design-hub"
RSH="ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

echo "==> [1/4] 构建前端 dist（每次无条件重建，杜绝 stale/漏建）"
( cd "$REPO/image-web" && npm ci --legacy-peer-deps && npm run build )
[ -f "$REPO/image-web/dist/index.html" ] || { echo "ERROR: 前端构建未产出 dist/index.html，中止部署"; exit 1; }

echo "==> [2/4] 源码 → app/（--delete 保持纯净；保护 Dockerfile/.dockerignore 不被删）"
rsync -az --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.mypy_cache/' --exclude '.ruff_cache/' --exclude '.pytest_cache/' \
  --exclude '*.db' --exclude 'generated/' --exclude 'assets/' --exclude 'exports/' \
  --exclude '.env' --exclude '.env.development' --exclude '.DS_Store' --exclude '.git/' \
  --exclude 'Dockerfile' --exclude '.dockerignore' \
  -e "$RSH" "$REPO/image-code/" "$HOST:$DEST/app/"

echo "==> [3/4] 部署产物 → design-hub/（含 app/Dockerfile、compose、nginx、scripts；不删服务器 .env/certs/web）"
rsync -az -e "$RSH" "$HERE/" "$HOST:$DEST/"

echo "==> [4/4] 前端 dist → web/（--delete 清旧 bundle；dist 必存在=步骤[1]产出）"
rsync -az --delete -e "$RSH" "$REPO/image-web/dist/" "$HOST:$DEST/web/"

echo "==> 推送完成。下一步在服务器重建（带迁移前 mysqldump 备份）："
echo "    $RSH $HOST 'cd $DEST && bash scripts/deploy.sh'"
echo "==> nginx conf 若有改动，deploy.sh 后另跑（零停机）："
echo "    $RSH $HOST 'docker exec design-hub-nginx nginx -t && docker exec design-hub-nginx nginx -s reload'"
