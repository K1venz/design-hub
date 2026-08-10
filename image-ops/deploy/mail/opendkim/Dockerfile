FROM debian:stable-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN sed -i \
        -e 's#http://deb.debian.org/debian-security#http://mirrors.aliyun.com/debian-security#g' \
        -e 's#http://deb.debian.org/debian#http://mirrors.aliyun.com/debian#g' \
        /etc/apt/sources.list.d/debian.sources \
    && apt-get update -o Acquire::ForceIPv4=true \
    && apt-get install -y --no-install-recommends \
        netcat-openbsd \
        opendkim \
        opendkim-tools \
        openssl \
        tini \
    && rm -rf /var/lib/apt/lists/*

COPY opendkim.conf /etc/opendkim.conf
COPY KeyTable SigningTable TrustedHosts /etc/opendkim/
COPY entrypoint.sh /usr/local/bin/opendkim-entrypoint

RUN chmod 0755 /usr/local/bin/opendkim-entrypoint \
    && mkdir -p /run/opendkim /etc/dkimkeys \
    && chown opendkim:opendkim /run/opendkim /etc/dkimkeys

EXPOSE 8891

ENTRYPOINT ["/usr/bin/tini", "--", "/usr/local/bin/opendkim-entrypoint"]
