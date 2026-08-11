#!/usr/bin/env bash
set -euo pipefail
umask 077
export MSYS2_ARG_CONV_EXCL='/CN=;/C='

script_dir="$(cd "$(dirname "$0")" && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

# shellcheck source=certificate-state.sh
source "$script_dir/certificate-state.sh"

legacy="$tmp_dir/legacy"
shared="$tmp_dir/shared"
mkdir -p "$legacy"
openssl req -x509 -nodes -newkey rsa:2048 \
  -keyout "$legacy/design-hub.key" -out "$legacy/design-hub.crt" \
  -days 1 -subj '/CN=image.sepaitech.com' >/dev/null 2>&1

ensure_shared_certificate "$shared" "$legacy" 192.0.2.10
cmp -s "$legacy/design-hub.crt" "$shared/design-hub.crt"
cmp -s "$legacy/design-hub.key" "$shared/design-hub.key"
[[ "$(stat -c '%a' "$shared/design-hub.crt")" == 600 ]]
[[ "$(stat -c '%a' "$shared/design-hub.key")" == 600 ]]
ensure_shared_certificate "$shared" "$legacy" 192.0.2.10

incomplete="$tmp_dir/incomplete"
mkdir -p "$incomplete"
cp "$legacy/design-hub.crt" "$incomplete/design-hub.crt"
if ensure_shared_certificate "$tmp_dir/incomplete-shared" "$incomplete" 192.0.2.10 \
  >/dev/null 2>&1; then
  echo "ERROR: incomplete legacy TLS material was accepted" >&2
  exit 1
fi

generated="$tmp_dir/generated"
ensure_shared_certificate "$generated" "$tmp_dir/missing-legacy" 192.0.2.10
validate_certificate_pair "$generated/design-hub.crt" "$generated/design-hub.key"
openssl x509 -in "$generated/design-hub.crt" -noout -ext subjectAltName \
  | grep -Fq 'IP Address:192.0.2.10'

echo "certificate state provisioning: OK"
