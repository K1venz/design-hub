FROM debian:stable-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i \
        -e 's#http://deb.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
        -e 's#http://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::ForceIPv4=true \
    && apt-get install -y --no-install-recommends \
        ca-certificates \
        gettext-base \
        netcat-openbsd \
        postfix \
        tini \
    && rm -rf /var/lib/apt/lists/* \
    && cp -a /var/spool/postfix /var/spool/postfix.seed

COPY main.cf.template /etc/postfix/main.cf.template
COPY entrypoint.sh /usr/local/bin/postfix-entrypoint

RUN chmod 0755 /usr/local/bin/postfix-entrypoint

EXPOSE 25

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/postfix-entrypoint"]
