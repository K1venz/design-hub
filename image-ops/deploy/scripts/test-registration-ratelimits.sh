#!/usr/bin/env bash
set -euo pipefail

script_dir="$(cd "$(dirname "$0")" && pwd)"
deploy_dir="$(cd "$script_dir/.." && pwd)"

if [[ "${1:-}" == "--verify" ]]; then
  config_path="$2"
  proxy_include="$3"
  verify_only=true
else
  config_path="$deploy_dir/nginx/conf.d/design-hub.conf"
  proxy_include="$deploy_dir/nginx/conf.d/proxy_backend.inc"
  verify_only=false
fi

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

function withoutComments(source) {
  let result = "";
  let quote = null;
  let escaped = false;

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (quote !== null) {
      result += character;
      if (escaped) {
        escaped = false;
      } else if (character === "\\") {
        escaped = true;
      } else if (character === quote) {
        quote = null;
      }
      continue;
    }
    if (character === '"' || character === "'") {
      quote = character;
      result += character;
      continue;
    }
    if (character === "#") {
      while (index < source.length && source[index] !== "\n") {
        index += 1;
      }
      if (index < source.length) result += "\n";
      continue;
    }
    result += character;
  }
  return result;
}

function parseBlocks(source) {
  const root = { header: "root", directives: [], blocks: [] };
  const stack = [root];
  let start = 0;

  function statement(end) {
    return source.slice(start, end).trim();
  }

  for (let index = 0; index < source.length; index += 1) {
    const character = source[index];
    if (character === ";") {
      const directive = statement(index);
      requireCondition(directive.length > 0, "empty nginx directive");
      stack.at(-1).directives.push(directive);
      start = index + 1;
    } else if (character === "{") {
      const header = statement(index);
      requireCondition(header.length > 0, "block without nginx header");
      const block = { header, directives: [], blocks: [] };
      stack.at(-1).blocks.push(block);
      stack.push(block);
      start = index + 1;
    } else if (character === "}") {
      requireCondition(stack.length > 1, "unexpected nginx closing brace");
      requireCondition(statement(index).length === 0, "nginx directive must end with a semicolon");
      stack.pop();
      start = index + 1;
    }
  }

  requireCondition(stack.length === 1, "unterminated nginx block");
  requireCondition(source.slice(start).trim().length === 0, "unterminated nginx directive");
  return root;
}

function normalize(value) {
  return value.replace(/\s+/g, " ").trim().replace(/;$/, "");
}

function hasDirective(block, directive) {
  const expected = normalize(directive);
  return block.directives.some((candidate) => normalize(candidate) === expected);
}

function hasZone(root, zone, rate) {
  return root.directives.some((directive) => new RegExp(
    `^limit_req_zone\\s+\\$binary_remote_addr\\s+zone=${escapeRegExp(zone)}:10m\\s+rate=${escapeRegExp(rate)}$`,
  ).test(normalize(directive)));
}

function secureServers(root) {
  return root.blocks.filter(
    (block) => normalize(block.header) === "server"
      && block.directives.some((directive) => /^listen 443(?: |$).*\bssl\b/.test(normalize(directive))),
  );
}

function exactHttpsLocation(servers, path) {
  const expected = `location = ${path}`;
  const locations = servers.flatMap((server) => server.blocks.filter(
    (block) => normalize(block.header) === expected,
  ));
  requireCondition(
    locations.length === 1,
    `expected exactly one HTTPS exact location for ${path}, found ${locations.length}`,
  );
  return locations[0];
}

const root = parseBlocks(withoutComments(config));
const proxyRoot = parseBlocks(withoutComments(proxy));

for (const directive of [
  "rewrite ^/api/(.*)$ /$1 break;",
  "proxy_pass http://design_hub_api;",
  "proxy_set_header Host              $host;",
  "proxy_set_header X-Real-IP         $remote_addr;",
  "proxy_set_header X-Forwarded-For   $proxy_add_x_forwarded_for;",
  "proxy_set_header X-Forwarded-Proto $scheme;",
]) {
  requireCondition(hasDirective(proxyRoot, directive), `proxy backend include missing: ${directive}`);
}
for (const directive of [
  "proxy_buffering off;",
  "proxy_cache off;",
  "proxy_read_timeout 3600s;",
  "proxy_send_timeout 3600s;",
  "chunked_transfer_encoding on;",
]) {
  requireCondition(hasDirective(proxyRoot, directive), `generation proxy control missing: ${directive}`);
}
requireCondition(hasDirective(root, "limit_req_status 429;"), "limit_req_status must return 429");

const routes = {
  "/api/auth/register": ["reg", "5r/m", "3"],
  "/api/auth/register/resend": ["reg_resend", "3r/m", "2"],
  "/api/auth/register/verify": ["reg_verify", "12r/m", "6"],
};
const servers = secureServers(root);
requireCondition(servers.length > 0, "missing HTTPS server with listen 443 ssl");
const genericApiLocations = servers.flatMap((server) => server.blocks.filter(
  (block) => normalize(block.header) === "location /api/",
));
requireCondition(
  genericApiLocations.length === 1,
  `expected exactly one HTTPS generic location for /api/, found ${genericApiLocations.length}`,
);
requireCondition(
  hasDirective(genericApiLocations[0], "include /etc/nginx/conf.d/proxy_backend.inc;"),
  "/api/ must preserve the shared API proxy semantics",
);
const maintenanceGuards = servers.flatMap((server) => server.blocks.filter(
  (block) => normalize(block.header) === "if (-f /etc/design-hub-state/maintenance)",
));
requireCondition(
  maintenanceGuards.length === 1,
  `expected exactly one HTTPS maintenance guard, found ${maintenanceGuards.length}`,
);
requireCondition(
  hasDirective(maintenanceGuards[0], "return 503;"),
  "maintenance guard must return 503",
);
for (const [path, [zone, rate, burst]] of Object.entries(routes)) {
  const block = exactHttpsLocation(servers, path);
  requireCondition(
    hasDirective(block, `limit_req zone=${zone} burst=${burst} nodelay;`),
    `${path} must use ${zone} with burst=${burst}`,
  );
  requireCondition(
    hasDirective(block, "include /etc/nginx/conf.d/proxy_backend.inc;"),
    `${path} must preserve the shared API proxy semantics`,
  );
  requireCondition(
    hasZone(root, zone, rate),
    `${zone} must be declared at ${rate}`,
  );
}

const login = exactHttpsLocation(servers, "/api/auth/login");
requireCondition(hasDirective(login, "limit_req zone=login burst=5 nodelay;"), "login rate limit changed");
requireCondition(hasDirective(login, "include /etc/nginx/conf.d/proxy_backend.inc;"), "login proxy semantics changed");
requireCondition(hasZone(root, "login", "15r/m"), "login zone declaration changed");

console.log("registration rate limits: OK");
NODE

if [[ "$verify_only" == true ]]; then
  exit 0
fi

tmp_dir="$(mktemp -d)"
trap 'rm -rf "$tmp_dir"' EXIT

node - "$config_path" "$proxy_include" "$tmp_dir" <<'NODE'
const fs = require("node:fs");
const path = require("node:path");

const [configPath, proxyPath, tempDir] = process.argv.slice(2);
const config = fs.readFileSync(configPath, "utf8");
const proxy = fs.readFileSync(proxyPath, "utf8");

function findBlock(source, header, from = 0) {
  const start = source.indexOf(header, from);
  if (start === -1) throw new Error(`missing fixture header: ${header}`);
  const openingBrace = source.indexOf("{", start);
  let depth = 1;
  let index = openingBrace + 1;
  while (depth > 0) {
    if (source[index] === "{") depth += 1;
    if (source[index] === "}") depth -= 1;
    index += 1;
  }
  return { start, end: index, text: source.slice(start, index) };
}

function replaceBlock(source, block, replacement) {
  return source.slice(0, block.start) + replacement + source.slice(block.end);
}

function serverWithListen(source, listen) {
  let from = 0;
  while (true) {
    const server = findBlock(source, "server {", from);
    if (server.text.includes(listen)) return server;
    from = server.end;
  }
}

const resend = findBlock(config, "location = /api/auth/register/resend {");
const verify = findBlock(config, "location = /api/auth/register/verify {");
const genericApi = findBlock(config, "location /api/ {");
const maintenanceGuard = findBlock(
  config,
  "if (-f /etc/design-hub-state/maintenance) {",
);

const fixtures = {
  "commented-route": {
    config: replaceBlock(config, resend, resend.text.split("\n").map((line) => `# ${line}`).join("\n")),
    proxy,
  },
  "duplicate-route": {
    config: config.slice(0, resend.end) + `\n${resend.text}` + config.slice(resend.end),
    proxy,
  },
  "non-https-route": {
    config: (() => {
      const withoutVerify = replaceBlock(config, verify, "");
      const updatedHttpServer = serverWithListen(withoutVerify, "listen 80;");
      return withoutVerify.slice(0, updatedHttpServer.end - 1)
        + `\n${verify.text}\n`
        + withoutVerify.slice(updatedHttpServer.end - 1);
    })(),
    proxy,
  },
  "commented-correct-proxy": {
    config,
    proxy: proxy.replace(
      "proxy_pass http://design_hub_api;",
      "# proxy_pass http://design_hub_api;\nproxy_pass http://wrong_upstream;",
    ),
  },
  "commented-limit-status": {
    config: config.replace("limit_req_status 429;", "# limit_req_status 429;"),
    proxy,
  },
  "commented-generation-proxy": {
    config,
    proxy: proxy.replace(
      "proxy_read_timeout        3600s;",
      "# proxy_read_timeout        3600s;\nproxy_read_timeout        5s;",
    ),
  },
  "commented-generic-location": {
    config: replaceBlock(
      config,
      genericApi,
      genericApi.text.split("\n").map((line) => `# ${line}`).join("\n"),
    ),
    proxy,
  },
  "missing-generic-location": {
    config: replaceBlock(config, genericApi, ""),
    proxy,
  },
  "missing-maintenance-guard": {
    config: replaceBlock(config, maintenanceGuard, ""),
    proxy,
  },
};

for (const [name, fixture] of Object.entries(fixtures)) {
  fs.writeFileSync(path.join(tempDir, `${name}.conf`), fixture.config);
  fs.writeFileSync(path.join(tempDir, `${name}.inc`), fixture.proxy);
}
NODE

accepted_fixtures=()
for fixture_path in "$tmp_dir"/*.conf; do
  fixture_name="$(basename "$fixture_path" .conf)"
  if bash "$0" --verify "$fixture_path" "$tmp_dir/$fixture_name.inc" >/dev/null 2>&1; then
    accepted_fixtures+=("$fixture_name")
  fi
done

if [[ "${#accepted_fixtures[@]}" -ne 0 ]]; then
  echo "ERROR: invalid fixtures accepted: ${accepted_fixtures[*]}" >&2
  exit 1
fi

echo "invalid fixture rejection: commented-route duplicate-route non-https-route commented-correct-proxy commented-limit-status commented-generation-proxy commented-generic-location missing-generic-location missing-maintenance-guard"
