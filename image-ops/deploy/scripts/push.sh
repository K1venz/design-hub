#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_source="${DEPLOY_SOURCE_DIR:-$(cd "$script_dir/.." && pwd)}"
repo_root="${REPO_ROOT:-$(cd "$deploy_source/../.." && pwd)}"
npm_bin="${NPM_BIN:-npm}"
release_id="${RELEASE_ID:-}"

if [[ -z "$release_id" ]]; then
  source_commit="$(git -C "$repo_root" rev-parse --short=12 HEAD)"
  release_id="${source_commit}-$(date -u +%Y%m%dT%H%M%SZ)"
else
  source_commit="$(git -C "$repo_root" rev-parse --short=12 HEAD 2>/dev/null || printf unknown)"
fi
if [[ ! "$release_id" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,79}$ ]]; then
  echo "ERROR: RELEASE_ID must be an immutable filesystem-safe identifier" >&2
  exit 1
fi

echo "==> [1/3] Building the SPA for release ${release_id}"
(
  cd "$repo_root/image-web"
  "$npm_bin" ci --legacy-peer-deps
  "$npm_bin" run build
)
[[ -f "$repo_root/image-web/dist/index.html" ]] || {
  echo "ERROR: frontend build did not produce dist/index.html" >&2
  exit 1
}

manifest_dir="$(mktemp -d)"
trap 'rm -rf "$manifest_dir"' EXIT
web_sha256="$(sha256sum "$repo_root/image-web/dist/index.html" | cut -d' ' -f1)"
cat > "$manifest_dir/release.env" <<ENV
RELEASE_ID=${release_id}
SOURCE_COMMIT=${source_commit}
WEB_INDEX_SHA256=${web_sha256}
ENV

copy_tree() {
  local source="$1"
  local destination="$2"
  shift 2
  mkdir -p "$destination"
  tar -C "$source" "$@" -cf - . | tar -C "$destination" -xf -
}

if [[ -n "${DEPLOY_LOCAL_ROOT:-}" ]]; then
  deploy_root="$DEPLOY_LOCAL_ROOT"
  incoming="$deploy_root/.incoming/$release_id"
  target="$deploy_root/releases/$release_id"
  if [[ -e "$incoming" || -e "$target" ]]; then
    echo "ERROR: release ${release_id} already exists" >&2
    exit 1
  fi

  echo "==> [2/3] Staging immutable release locally"
  mkdir -p "$incoming" "$deploy_root/releases"
  copy_tree "$repo_root/image-code" "$incoming/app" \
    --exclude=.venv --exclude=__pycache__ --exclude='*.pyc' \
    --exclude=.mypy_cache --exclude=.ruff_cache --exclude=.pytest_cache \
    --exclude='*.db' --exclude=generated --exclude=assets --exclude=exports \
    --exclude=.env --exclude=.env.development --exclude=.git
  copy_tree "$deploy_source" "$incoming/deploy" --exclude=.env --exclude=nginx/certs
  copy_tree "$repo_root/image-web/dist" "$incoming/web"
  cp "$manifest_dir/release.env" "$incoming/release.env"
  [[ -f "$incoming/app/pyproject.toml" || -f "$incoming/app/app.txt" ]]
  [[ -f "$incoming/web/index.html" ]]
  [[ -f "$incoming/deploy/compose.yml" ]]
  mv "$incoming" "$target"
else
  key="${DEPLOY_KEY:-$HOME/.ssh/dh_deploy_ed25519}"
  host="${DEPLOY_HOST:-root@203.0.113.10}"
  deploy_root="${DEPLOY_ROOT:-/opt/docker/design-hub}"
  rsh="ssh -i $key -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null"
  incoming="$deploy_root/.incoming/$release_id"
  target="$deploy_root/releases/$release_id"

  echo "==> [2/3] Uploading only to ${incoming}"
  ssh -i "$key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$host" \
    "set -eu; test ! -e '$incoming'; test ! -e '$target'; mkdir -p '$incoming/app' '$incoming/deploy' '$incoming/web' '$deploy_root/releases'"
  rsync -az --delete \
    --exclude '.venv/' --exclude '__pycache__/' --exclude '*.pyc' \
    --exclude '.mypy_cache/' --exclude '.ruff_cache/' --exclude '.pytest_cache/' \
    --exclude '*.db' --exclude 'generated/' --exclude 'assets/' --exclude 'exports/' \
    --exclude '.env' --exclude '.env.development' --exclude '.DS_Store' --exclude '.git/' \
    -e "$rsh" "$repo_root/image-code/" "$host:$incoming/app/"
  rsync -az --delete --exclude '.env' --exclude 'nginx/certs/' \
    -e "$rsh" "$deploy_source/" "$host:$incoming/deploy/"
  rsync -az --delete -e "$rsh" "$repo_root/image-web/dist/" "$host:$incoming/web/"
  rsync -az -e "$rsh" "$manifest_dir/release.env" "$host:$incoming/release.env"
  ssh -i "$key" -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null "$host" \
    "set -eu; test -f '$incoming/app/pyproject.toml'; test -f '$incoming/web/index.html'; test -f '$incoming/deploy/compose.yml'; mv '$incoming' '$target'"
fi

echo "==> [3/3] RELEASE_STAGED=${release_id}"
if [[ -z "${DEPLOY_LOCAL_ROOT:-}" ]]; then
  echo "Run: ssh ${host} 'bash ${target}/deploy/scripts/deploy.sh ${release_id}'"
fi
