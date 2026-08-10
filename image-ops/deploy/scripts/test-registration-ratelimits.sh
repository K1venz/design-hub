#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"
config_path="${1:-$deploy_dir/nginx/conf.d/design-hub.conf}"
proxy_include="$deploy_dir/nginx/conf.d/proxy_backend.inc"

node - "$config_path" "$proxy_include" <<'NODE'
const fs = require("node:fs");

const [configPath, proxyPath] = process.argv.slice(2);
const config = fs.readFileSync(configPath, "utf8");
const proxy = fs.readFileSync(proxyPath, "utf8");

function requireCondition(condition, message) {
  if (!condition) {
    throw new Error(message);
  }
}

function escapeRegExp(value) {
  return value.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
}

function exactLocation(path) {
  const match = new RegExp(`location\\s*=\\s*${escapeRegExp(path)}\\s*\\{`).exec(config);
  requireCondition(match, `missing exact location for ${path}`);

  let depth = 1;
  let index = match.index + match[0].length;
  while (depth > 0) {
    requireCondition(index < config.length, `unterminated location for ${path}`);
    if (config[index] === "{") depth += 1;
    if (config[index] === "}") depth -= 1;
    index += 1;
  }
  return config.slice(match.index + match[0].length, index - 1);
}

for (const directive of [
  "rewrite ^/api/(.*)$ /$1 break;",
  "proxy_pass http://design_hub_api;",
  "proxy_set_header Host              $host;",
  "proxy_set_header X-Real-IP         $remote_addr;",
  "proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;",
  "proxy_set_header X-Forwarded-Proto $scheme;",
]) {
  requireCondition(proxy.includes(directive), `proxy backend include missing: ${directive}`);
}

const routes = {
  "/api/auth/register": ["reg", "5r/m", "3"],
  "/api/auth/register/resend": ["reg_resend", "3r/m", "2"],
  "/api/auth/register/verify": ["reg_verify", "12r/m", "6"],
};
for (const [path, [zone, rate, burst]] of Object.entries(routes)) {
  const block = exactLocation(path);
  requireCondition(
    new RegExp(`limit_req\\s+zone=${escapeRegExp(zone)}\\s+burst=${burst}\\s+nodelay\\s*;`).test(block),
    `${path} must use ${zone} with burst=${burst}`,
  );
  requireCondition(
    block.includes("include /etc/nginx/conf.d/proxy_backend.inc;"),
    `${path} must preserve the shared API proxy semantics`,
  );
  requireCondition(
    new RegExp(`limit_req_zone\\s+\\$binary_remote_addr\\s+zone=${escapeRegExp(zone)}:10m\\s+rate=${escapeRegExp(rate)}\\s*;`).test(config),
    `${zone} must be declared at ${rate}`,
  );
}

const login = exactLocation("/api/auth/login");
requireCondition(login.includes("limit_req zone=login burst=5 nodelay;"), "login rate limit changed");
requireCondition(login.includes("include /etc/nginx/conf.d/proxy_backend.inc;"), "login proxy semantics changed");

console.log("registration rate limits: OK");
NODE
