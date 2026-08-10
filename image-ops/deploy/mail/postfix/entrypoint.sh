#!/usr/bin/env bash
set -euo pipefail

: "${MAIL_HOSTNAME:?MAIL_HOSTNAME is required}"
: "${MAIL_DOMAIN:?MAIL_DOMAIN is required}"
: "${MAIL_NETWORKS:?MAIL_NETWORKS is required}"

if [[ ! -d /var/spool/postfix/maildrop ]]; then
  cp -a /var/spool/postfix.seed/. /var/spool/postfix/
fi

envsubst '${MAIL_HOSTNAME} ${MAIL_DOMAIN} ${MAIL_NETWORKS}' \
  < /etc/postfix/main.cf.template \
  > /etc/postfix/main.cf

postfix check

exec postfix start-fg
