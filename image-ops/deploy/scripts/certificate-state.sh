#!/usr/bin/env bash

validate_certificate_pair() {
  local certificate="$1"
  local private_key="$2"
  local certificate_public_key
  local private_public_key

  [[ -f "$certificate" && ! -L "$certificate" && -s "$certificate" ]] || return 1
  [[ -f "$private_key" && ! -L "$private_key" && -s "$private_key" ]] || return 1
  certificate_public_key="$(openssl x509 -in "$certificate" -pubkey -noout | openssl sha256)" || return 1
  private_public_key="$(openssl pkey -in "$private_key" -pubout | openssl sha256)" || return 1
  [[ "$certificate_public_key" == "$private_public_key" ]]
}

ensure_shared_certificate() {
  local shared_directory="$1"
  local legacy_directory="$2"
  local server_ip="$3"
  local certificate="$shared_directory/design-hub.crt"
  local private_key="$shared_directory/design-hub.key"
  local legacy_certificate="$legacy_directory/design-hub.crt"
  local legacy_private_key="$legacy_directory/design-hub.key"
  local temporary_certificate
  local temporary_private_key

  mkdir -p "$shared_directory"
  if [[ -e "$certificate" || -L "$certificate" || -e "$private_key" || -L "$private_key" ]]; then
    validate_certificate_pair "$certificate" "$private_key" || {
      echo "ERROR: shared TLS certificate and private key are incomplete or mismatched" >&2
      return 1
    }
    chmod 600 "$certificate" "$private_key"
    return 0
  fi

  temporary_certificate="$(mktemp "$shared_directory/.design-hub.crt.XXXXXX")" || return 1
  temporary_private_key="$(mktemp "$shared_directory/.design-hub.key.XXXXXX")" || {
    rm -f "$temporary_certificate"
    return 1
  }
  if [[ -e "$legacy_certificate" || -L "$legacy_certificate" \
    || -e "$legacy_private_key" || -L "$legacy_private_key" ]]; then
    if ! validate_certificate_pair "$legacy_certificate" "$legacy_private_key" \
      || ! cp "$legacy_certificate" "$temporary_certificate" \
      || ! cp "$legacy_private_key" "$temporary_private_key"; then
      rm -f "$temporary_certificate" "$temporary_private_key"
      echo "ERROR: legacy TLS certificate and private key are incomplete or mismatched" >&2
      return 1
    fi
  elif ! openssl req -x509 -nodes -newkey rsa:2048 \
    -keyout "$temporary_private_key" -out "$temporary_certificate" \
    -days 825 -subj "/C=CN/O=design-hub/CN=design-hub.local" \
    -addext "subjectAltName=IP:${server_ip},DNS:design-hub.local" 2>/dev/null; then
    rm -f "$temporary_certificate" "$temporary_private_key"
    return 1
  fi

  chmod 600 "$temporary_certificate" "$temporary_private_key"
  validate_certificate_pair "$temporary_certificate" "$temporary_private_key" || {
    rm -f "$temporary_certificate" "$temporary_private_key"
    return 1
  }
  mv -f "$temporary_private_key" "$private_key"
  mv -f "$temporary_certificate" "$certificate"
}
