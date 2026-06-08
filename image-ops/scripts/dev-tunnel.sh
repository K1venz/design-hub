#!/usr/bin/env bash
# dev-tunnel.sh — READ-ONLY SSH tunnel to prod backend for local 联调.
#
# Forwards localhost:<LOCAL_PORT> on this machine straight to the prod api
# CONTAINER's uvicorn port (8000), bypassing nginx. Mapping the container port
# (not nginx 443) is intentional (per backend / ISSUE-0011):
#   * SSE 逐张 events are not buffered (we hit uvicorn directly);
#   * the ?access_token= query string is preserved end-to-end (SSE auth);
#   * plain http + root paths (no /api prefix, no self-signed cert) — the
#     frontend points VITE_API_TARGET at http://localhost:<LOCAL_PORT> and the
#     paths match openapi.json verbatim (/uploads, /listing/jobs, ...).
#
# SCOPE — READ ONLY. This tunnel reaches the REAL prod DB + prod TOS + real gpt
# billing. Use it ONLY for browsing existing data (history/回显走查, GET 列表/详情,
# 越权 404/401 读类校验). DO NOT POST/create through it: POST /listing/generate
# here = pollutes prod DB + spends real gpt money. Write/create tests (A 出图链路,
# E 成本, B 落库) belong on the separate controlled test env, NOT this tunnel.
#
# The api container IP is resolved dynamically each run (it can change across
# restarts), so this keeps working after a redeploy.
#
# Usage:
#   ./dev-tunnel.sh                 # tunnel on default port 8443 (Ctrl-C to stop)
#   LOCAL_PORT=9443 ./dev-tunnel.sh
set -euo pipefail

PROD_HOST="${PROD_HOST:-203.0.113.10}"
PROD_USER="${PROD_USER:-root}"
SSH_KEY="${SSH_KEY:-$HOME/.ssh/dh_deploy_ed25519}"
LOCAL_PORT="${LOCAL_PORT:-8443}"
API_CONTAINER="${API_CONTAINER:-design-hub-api}"
API_NETWORK="${API_NETWORK:-design-hub_default}"
API_PORT="${API_PORT:-8000}"

echo "[dev-tunnel] resolving ${API_CONTAINER} IP on ${API_NETWORK} ..."
API_IP="$(ssh -i "${SSH_KEY}" -o BatchMode=yes -o ConnectTimeout=10 "${PROD_USER}@${PROD_HOST}" \
  "docker inspect -f '{{(index .NetworkSettings.Networks \"${API_NETWORK}\").IPAddress}}' ${API_CONTAINER}")"
if [[ -z "${API_IP}" ]]; then
  echo "[dev-tunnel] ERROR: could not resolve api container IP" >&2
  exit 1
fi

echo "[dev-tunnel] localhost:${LOCAL_PORT}  ->  ${PROD_USER}@${PROD_HOST}  ->  ${API_IP}:${API_PORT} (uvicorn, bypassing nginx)"
echo "[dev-tunnel] point vite at:  VITE_API_TARGET=http://localhost:${LOCAL_PORT}"
echo "[dev-tunnel] READ ONLY — do not POST/create through this tunnel (real prod DB + gpt billing)."
echo "[dev-tunnel] Ctrl-C to stop."

exec ssh -i "${SSH_KEY}" -N \
  -o ExitOnForwardFailure=yes \
  -o ServerAliveInterval=30 \
  -o ServerAliveCountMax=3 \
  -L "${LOCAL_PORT}:${API_IP}:${API_PORT}" \
  "${PROD_USER}@${PROD_HOST}"
