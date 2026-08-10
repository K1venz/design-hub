#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

export ENV_FILE="$tmp_dir/.env"
: > "$ENV_FILE"

# shellcheck source=mail-env.sh
source "$script_dir/mail-env.sh"

ensure_mail_env
first_pepper="$(awk -F= '$1 == "EMAIL_VERIFICATION_CODE_PEPPER" {print $2}' "$ENV_FILE")"
ensure_mail_env
second_pepper="$(awk -F= '$1 == "EMAIL_VERIFICATION_CODE_PEPPER" {print $2}' "$ENV_FILE")"

[[ "$first_pepper" =~ ^[0-9a-f]{64}$ ]]
[[ "$second_pepper" == "$first_pepper" ]]

assert_single_env_entry() {
  local key="$1"
  local expected="$2"

  [[ "$(grep -c "^${key}=" "$ENV_FILE")" -eq 1 ]]
  [[ "$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2-)" == "$expected" ]]
}

assert_single_env_entry MAIL_DELIVERY_MODE smtp
assert_single_env_entry SMTP_HOST smtp
assert_single_env_entry SMTP_PORT 25
assert_single_env_entry SMTP_USERNAME ""
assert_single_env_entry SMTP_PASSWORD ""
assert_single_env_entry SMTP_FROM_NAME "Design Hub"
assert_single_env_entry SMTP_FROM no-reply@image.sepaitech.com
assert_single_env_entry SMTP_USE_TLS false
[[ "$(grep -Fxc 'SMTP_FROM_NAME=Design Hub' "$ENV_FILE")" -eq 1 ]]
[[ "$(grep -c '^EMAIL_VERIFICATION_CODE_PEPPER=' "$ENV_FILE")" -eq 1 ]]
! grep -q '^PASSWORD_RESET_CODE_PEPPER=' "$ENV_FILE"

cp "$ENV_FILE" "$tmp_dir/conflict.env"
sed -i 's/^SMTP_FROM_NAME=.*/SMTP_FROM_NAME=Unexpected Sender/' "$tmp_dir/conflict.env"
if (
  ENV_FILE="$tmp_dir/conflict.env"
  ensure_mail_env
) >/dev/null 2>&1; then
  echo "ERROR: conflicting SMTP_FROM_NAME was accepted" >&2
  exit 1
fi

echo "mail environment provisioning: OK"
