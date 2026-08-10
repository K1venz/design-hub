#!/usr/bin/env bash
set -euo pipefail

key=/etc/dkimkeys/designhub.private
if [[ ! -s "$key" ]]; then
  echo "ERROR: DKIM private key is missing: $key" >&2
  exit 1
fi

chown opendkim:opendkim /etc/dkimkeys "$key"
chmod 0700 /etc/dkimkeys
chmod 0600 "$key"
mkdir -p /run/opendkim
chown opendkim:opendkim /run/opendkim

opendkim -n -x /etc/opendkim.conf
exec opendkim -f -x /etc/opendkim.conf
