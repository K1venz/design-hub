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
first_pepper="$(awk -F= '$1 == "PASSWORD_RESET_CODE_PEPPER" {print $2}' "$ENV_FILE")"
ensure_mail_env
second_pepper="$(awk -F= '$1 == "PASSWORD_RESET_CODE_PEPPER" {print $2}' "$ENV_FILE")"

[[ "$first_pepper" =~ ^[0-9a-f]{64}$ ]]
[[ "$second_pepper" == "$first_pepper" ]]

python3 - "$ENV_FILE" <<'PY'
from collections import Counter
from pathlib import Path
import sys

rows = [line.split("=", 1) for line in Path(sys.argv[1]).read_text().splitlines() if line]
values = dict(rows)
counts = Counter(key for key, _ in rows)
expected = {
    "MAIL_DELIVERY_MODE": "smtp",
    "SMTP_HOST": "smtp",
    "SMTP_PORT": "25",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_FROM": "no-reply@image.sepaitech.com",
    "SMTP_USE_TLS": "false",
}
for key, value in expected.items():
    assert values[key] == value, (key, values.get(key))
    assert counts[key] == 1, (key, counts[key])
assert counts["PASSWORD_RESET_CODE_PEPPER"] == 1
PY

cp "$ENV_FILE" "$tmp_dir/conflict.env"
sed -i 's/^SMTP_HOST=.*/SMTP_HOST=unexpected/' "$tmp_dir/conflict.env"
if (
  ENV_FILE="$tmp_dir/conflict.env"
  ensure_mail_env
) >/dev/null 2>&1; then
  echo "ERROR: conflicting SMTP_HOST was accepted" >&2
  exit 1
fi

echo "mail environment provisioning: OK"
