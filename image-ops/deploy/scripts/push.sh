#!/usr/bin/env bash
# 本地执行：把源码 + 部署产物 + 前端 dist 推到服务器。推完在服务器跑 deploy.sh 重建。
# 用法：bash image-ops/deploy/scripts/push.sh
# 可用环境变量覆盖：DEPLOY_KEY、DEPLOY_HOST
set -euo pipefail

HERE="$(cd "$(dirname "$0")/.." && pwd)"   # image-ops/deploy
REPO="$(cd "$HERE/../.." && pwd)"          # image-gen 仓库根
KEY="${DEPLOY_KEY:-$HOME/.ssh/dh_deploy_ed25519}"
HOST="${DEPLOY_HOST:-root@14.103.51.191}"
DEST="/opt/docker/design-hub"
RSH="ssh -i $KEY -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"

echo "==> [1/3] 源码 → app/（--delete 保持纯净；保护 Dockerfile/.dockerignore 不被删）"
rsync -az --delete \
  --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
  --exclude '.mypy_cache/' --exclude '.ruff_cache/' --exclude '.pytest_cache/' \
  --exclude '*.db' --exclude 'generated/' --exclude 'assets/' --exclude 'exports/' \
  --exclude '.env' --exclude '.env.development' --exclude '.DS_Store' --exclude '.git/' \
  --exclude 'Dockerfile' --exclude '.dockerignore' \
  -e "$RSH" "$REPO/image-code/" "$HOST:$DEST/app/"

echo "==> [2/3] 部署产物 → design-hub/（含 app/Dockerfile、compose、nginx、scripts；不删服务器 .env/certs/web）"
rsync -az -e "$RSH" "$HERE/" "$HOST:$DEST/"

echo "==> [3/3] 前端 dist → web/（若存在）"
if [ -d "$REPO/image-web/dist" ]; then
  rsync -az --delete -e "$RSH" "$REPO/image-web/dist/" "$HOST:$DEST/web/"
else
  echo "    (无 image-web/dist，跳过；需先在 image-web 里构建)"
fi

echo "==> 完成。重建/启动："
echo "    $RSH $HOST 'cd $DEST && bash scripts/deploy.sh'"
