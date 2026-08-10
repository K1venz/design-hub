#!/usr/bin/env bash

ENV_FILE="${ENV_FILE:-.env}"

snapshot_environment() {
  local source_file="$1"
  local snapshot_file="$2"
  local snapshot_dir
  local temporary

  [[ -f "$source_file" ]] || {
    echo "ERROR: environment file is missing" >&2
    return 1
  }
  snapshot_dir="$(dirname "$snapshot_file")"
  mkdir -p "$snapshot_dir"
  temporary="${snapshot_file}.tmp.$$"
  umask 077
  cp "$source_file" "$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$snapshot_file"
}

restore_environment() {
  local snapshot_file="$1"
  local destination_file="$2"
  local temporary

  [[ -f "$snapshot_file" ]] || {
    echo "ERROR: environment snapshot is missing" >&2
    return 1
  }
  temporary="${destination_file}.restore.$$"
  umask 077
  cp "$snapshot_file" "$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$destination_file"
}

migrate_legacy_mail_env() {
  local legacy_count
  local current_count
  local legacy_value
  local current_value
  local temporary

  [[ -f "$ENV_FILE" ]] || {
    echo "ERROR: environment file is missing" >&2
    return 1
  }
  legacy_count="$(grep -c '^PASSWORD_RESET_CODE_PEPPER=' "$ENV_FILE" || true)"
  current_count="$(grep -c '^EMAIL_VERIFICATION_CODE_PEPPER=' "$ENV_FILE" || true)"
  if [[ "$legacy_count" -gt 1 || "$current_count" -gt 1 ]]; then
    echo "ERROR: duplicate mail pepper key in environment" >&2
    return 1
  fi
  [[ "$legacy_count" -eq 1 ]] || return 0

  legacy_value="$(grep -E '^PASSWORD_RESET_CODE_PEPPER=' "$ENV_FILE" | cut -d= -f2-)"
  if [[ ! "$legacy_value" =~ ^[0-9a-f]{64}$ ]]; then
    echo "ERROR: legacy mail pepper must be 64 lowercase hexadecimal characters" >&2
    return 1
  fi
  if [[ "$current_count" -eq 1 ]]; then
    current_value="$(grep -E '^EMAIL_VERIFICATION_CODE_PEPPER=' "$ENV_FILE" | cut -d= -f2-)"
    if [[ "$current_value" != "$legacy_value" ]]; then
      echo "ERROR: legacy and current mail pepper values conflict" >&2
      return 1
    fi
  fi

  temporary="${ENV_FILE}.migrate.$$"
  umask 077
  awk -F= -v has_current="$current_count" '
    $1 == "PASSWORD_RESET_CODE_PEPPER" {
      if (has_current == 0) {
        sub(/^PASSWORD_RESET_CODE_PEPPER=/, "EMAIL_VERIFICATION_CODE_PEPPER=")
        print
      }
      next
    }
    { print }
  ' "$ENV_FILE" > "$temporary"
  chmod 600 "$temporary"
  mv -f "$temporary" "$ENV_FILE"
  unset legacy_value current_value
}

reject_legacy_mail_env() {
  if grep -q '^PASSWORD_RESET_CODE_PEPPER=' "$ENV_FILE"; then
    echo "ERROR: PASSWORD_RESET_CODE_PEPPER requires an explicit environment migration" >&2
    return 1
  fi
}

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
  reject_legacy_mail_env || return 1
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
