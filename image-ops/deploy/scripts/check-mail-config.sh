#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

example_env_path="${ENV_EXAMPLE_PATH:-.env.example}"
python_bin="${PYTHON_BIN:-python3}"

"$python_bin" - "$example_env_path" <<'PY'
from pathlib import Path
import sys

values = {}
for raw_line in Path(sys.argv[1]).read_text(encoding="utf-8").splitlines():
    line = raw_line.strip()
    if not line or line.startswith("#"):
        continue
    key, value = line.split("=", 1)
    if key in values:
        raise SystemExit(f"duplicate example environment key: {key}")
    values[key] = value

if "PASSWORD_RESET_CODE_PEPPER" in values:
    raise SystemExit("PASSWORD_RESET_CODE_PEPPER is no longer supported")

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

if [[ -n "${COMPOSE_CONFIG_JSON:-}" ]]; then
  config_json="$COMPOSE_CONFIG_JSON"
else
  config_json="$(docker compose config --format json)"
fi
"$python_bin" -c '
import json
import os
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

release_id = os.environ["RELEASE_ID"]
release_dir = os.environ["DESIGN_HUB_RELEASE_DIR"]
state_dir = os.environ["DESIGN_HUB_STATE_DIR"]
image_repository = os.environ.get("API_IMAGE_REPOSITORY", "design-hub-api")
expected_image = f"{image_repository}:{release_id}"
for name in ("api", "worker"):
    if services[name].get("image") != expected_image:
        raise SystemExit(f"{name} does not use immutable image {expected_image}")
for name in ("api", "worker", "nginx"):
    labels = services[name].get("labels", {})
    if labels.get("com.design-hub.release") != release_id:
        raise SystemExit(f"{name} is missing release identity label")

def mounted_source(service, target):
    for volume in service.get("volumes", []):
        if isinstance(volume, dict) and volume.get("target") == target:
            return volume.get("source")
        if isinstance(volume, str):
            source, mounted, *_ = volume.split(":")
            if mounted == target:
                return source
    return None

nginx = services["nginx"]
if mounted_source(nginx, "/usr/share/nginx/html") != f"{release_dir}/web":
    raise SystemExit("nginx web mount is not bound to the selected versioned release")
if mounted_source(nginx, "/etc/design-hub-state") != state_dir:
    raise SystemExit("nginx is missing the maintenance-state mount")

dkim_health = services["dkim"].get("healthcheck", {}).get("test", [])
if dkim_health != ["CMD-SHELL", "nc -z 127.0.0.1 8891"]:
    raise SystemExit(f"unexpected dkim health check: {dkim_health}")
' <<<"$config_json"

echo "mail compose configuration: OK"
