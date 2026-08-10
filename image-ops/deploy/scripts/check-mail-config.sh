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
' <<<"$config_json"

echo "mail compose configuration: OK"
