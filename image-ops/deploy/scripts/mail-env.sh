#!/usr/bin/env bash

ENV_FILE="${ENV_FILE:-.env}"

ensure_env_value() {
  local key="$1"
  local expected="$2"
  local count
  local current

  count="$(grep -c "^${key}=" "$ENV_FILE" || true)"
  if [[ "$count" -gt 1 ]]; then
    echo "ERROR: ${ENV_FILE} contains duplicate ${key}" >&2
    return 1
  fi
  if [[ "$count" -eq 0 ]]; then
    printf '%s=%s\n' "$key" "$expected" >> "$ENV_FILE"
    return
  fi

  current="$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2-)"
  if [[ -z "$current" && -n "$expected" ]]; then
    sed -i "s#^${key}=.*#${key}=${expected}#" "$ENV_FILE"
  elif [[ "$current" != "$expected" ]]; then
    echo "ERROR: ${key} conflicts with the internal SMTP design" >&2
    return 1
  fi
}

ensure_generated_hex() {
  local key="$1"
  local bytes="$2"
  local expected_length=$((bytes * 2))
  local count
  local current
  local generated

  count="$(grep -c "^${key}=" "$ENV_FILE" || true)"
  if [[ "$count" -gt 1 ]]; then
    echo "ERROR: ${ENV_FILE} contains duplicate ${key}" >&2
    return 1
  fi
  if [[ "$count" -eq 0 ]]; then
    generated="$(openssl rand -hex "$bytes")"
    printf '%s=%s\n' "$key" "$generated" >> "$ENV_FILE"
    unset generated
    return
  fi

  current="$(grep -E "^${key}=" "$ENV_FILE" | cut -d= -f2-)"
  if [[ -z "$current" ]]; then
    generated="$(openssl rand -hex "$bytes")"
    sed -i "s#^${key}=.*#${key}=${generated}#" "$ENV_FILE"
    unset generated
    return
  fi
  if [[ ! "$current" =~ ^[0-9a-f]+$ || "${#current}" -ne "$expected_length" ]]; then
    echo "ERROR: ${key} must be ${expected_length} lowercase hexadecimal characters" >&2
    return 1
  fi
}

ensure_mail_env() {
  ensure_env_value MAIL_DELIVERY_MODE smtp || return 1
  ensure_env_value SMTP_HOST smtp || return 1
  ensure_env_value SMTP_PORT 25 || return 1
  ensure_env_value SMTP_USERNAME "" || return 1
  ensure_env_value SMTP_PASSWORD "" || return 1
  ensure_env_value SMTP_FROM_NAME "Design Hub" || return 1
  ensure_env_value SMTP_FROM no-reply@image.sepaitech.com || return 1
  ensure_env_value SMTP_USE_TLS false || return 1
  ensure_generated_hex EMAIL_VERIFICATION_CODE_PEPPER 32 || return 1
  chmod 600 "$ENV_FILE"
}
