#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

config_json="$(docker compose config --format json)"
python3 -c '
import json
import sys

config = json.load(sys.stdin)
services = config["services"]
for name in ("api", "dkim", "smtp"):
    if name not in services:
        raise SystemExit(f"missing compose service: {name}")

smtp = services["smtp"]
if smtp.get("ports"):
    raise SystemExit("smtp must not publish a host port")
if "25" not in {str(port) for port in smtp.get("expose", [])}:
    raise SystemExit("smtp must expose container port 25")

mail_network = config["networks"]["mail"]
subnets = {
    item["subnet"]
    for item in mail_network.get("ipam", {}).get("config", [])
}
if subnets != {"172.29.0.0/24"}:
    raise SystemExit(f"unexpected mail network: {sorted(subnets)}")

if "mail" not in services["api"].get("networks", {}):
    raise SystemExit("api is not attached to the mail network")
if "mail" in services["worker"].get("networks", {}):
    raise SystemExit("worker must not be attached to the mail network")

dkim_health = services["dkim"].get("healthcheck", {}).get("test", [])
if dkim_health != ["CMD-SHELL", "nc -z 127.0.0.1 8891"]:
    raise SystemExit(f"unexpected dkim health check: {dkim_health}")
' <<<"$config_json"

python3 - .env.example <<'PY'
from pathlib import Path
import sys

values = {}
for raw_line in Path(sys.argv[1]).read_text().splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    key, value = line.split("=", 1)
    if key in values:
        raise SystemExit(f"duplicate example environment key: {key}")
    values[key] = value

expected = {
    "MAIL_DELIVERY_MODE": "smtp",
    "SMTP_HOST": "smtp",
    "SMTP_PORT": "25",
    "SMTP_USERNAME": "",
    "SMTP_PASSWORD": "",
    "SMTP_FROM_NAME": "Design Hub",
    "SMTP_FROM": "no-reply@image.sepaitech.com",
    "SMTP_USE_TLS": "false",
    "EMAIL_VERIFICATION_CODE_PEPPER": "__GENERATED_64_HEX__",
}
for key, value in expected.items():
    if values.get(key) != value:
        raise SystemExit(f"unexpected {key} in .env.example")
PY

echo "mail compose configuration: OK"
