# design-hub 生产部署与邮件运维

当前生产栈由前端 SPA、FastAPI、Generation Worker、Redis、Postfix、OpenDKIM、nginx 和现有 MySQL 8.4 组成。忘记密码邮件使用服务器内自建 SMTP 投递，发件人为 `no-reply@image.sepaitech.com`。

完整设计与安全边界见 [`docs/superpowers/specs/2026-08-10-internal-smtp-design.md`](../docs/superpowers/specs/2026-08-10-internal-smtp-design.md)。

## 服务器与目录

- 服务器：`14.103.51.191`（Ubuntu 24.04）
- 应用目录：`/opt/docker/design-hub`
- 持久化目录：`/data/docker/design-hub`
- 现有 MySQL：`/opt/docker/mysql`，外部 Docker 网络 `mysql_default`

```text
/opt/docker/design-hub/
├── compose.yml
├── .env                         # 生产密钥，仅服务器保存，权限 600
├── app/                         # image-code 构建上下文
├── mail/
│   ├── postfix/
│   └── opendkim/
├── nginx/
├── scripts/
└── web/

/data/docker/design-hub/
├── redis/
├── generated/
├── assets/
├── exports/
└── mail/
    ├── spool/                   # Postfix 队列
    ├── dkim/                    # DKIM 私钥和公开记录，权限 700
    └── dns-records.txt          # 部署生成的 DNS 配置清单
```

## 邮件网络与安全边界

- `mail` 网络固定为 `172.29.0.0/24`。
- Postfix 固定地址 `172.29.0.10`，OpenDKIM 固定地址 `172.29.0.11`。
- 只有 API 接入 `mail` 网络；Worker、nginx、Redis 均无法连接 SMTP。
- SMTP 仅在容器网络暴露 25 端口，不映射到宿主机，不是公网开放中继。
- Postfix 只信任回环地址和 `172.29.0.0/24`，其他来源直接拒绝。
- API 使用 `SMTP_HOST=smtp`、`SMTP_PORT=25`、无认证、无 TLS；这是受限 Docker 内网连接。
- `PASSWORD_RESET_CODE_PEPPER` 独立于 JWT 密钥，由部署脚本生成 64 位十六进制随机值。
- OpenDKIM 私钥只保存在 `/data/docker/design-hub/mail/dkim/designhub.private`，不进入代码仓库或应用容器。

## 部署

本地推送会保护服务器上的 `.env`、证书和现有前端文件：

```bash
bash image-ops/deploy/scripts/push.sh
```

服务器执行：

```bash
cd /opt/docker/design-hub
bash scripts/deploy.sh
```

部署脚本幂等完成以下工作：

1. 创建持久化目录和本地 TLS 证书。
2. 保留现有 `.env`，补齐并严格校验 Redis、SMTP 和密码重置密钥。
3. 校验 compose、安全网络与示例环境配置。
4. 构建镜像；首次部署生成 2048 位 DKIM 密钥和 DNS 清单。
5. 启动 Redis、OpenDKIM、Postfix，并分别执行健康检查。
6. 从 API 容器执行 Redis PING 和 SMTP NOOP，不发送外部邮件。
7. 备份 MySQL、执行 Alembic 迁移、启动完整栈并平滑重载 nginx。

任何已有固定邮件配置与设计不一致时，脚本会直接失败，不会静默覆盖。DKIM 密钥只在两个文件均不存在时生成；出现残缺密钥对时也会直接失败。

## DNS 与 PTR

部署完成后读取：

```bash
cat /data/docker/design-hub/mail/dns-records.txt
```

需要配置以下记录，DKIM 的 `p=` 值以服务器生成文件为准：

```text
smtp.image.sepaitech.com A 14.103.51.191
image.sepaitech.com TXT "v=spf1 ip4:14.103.51.191 -all"
designhub._domainkey.image.sepaitech.com TXT "v=DKIM1; ...; p=..."
_dmarc.image.sepaitech.com TXT "v=DMARC1; p=none"
14.103.51.191 PTR smtp.image.sepaitech.com
```

PTR 记录必须在云服务器/IP 服务商控制台配置。DNS 生效前，容器健康不等于外部收件箱可达；主流邮箱可能拒收或归入垃圾邮件。

验证命令：

```bash
dig +short smtp.image.sepaitech.com A
dig +short image.sepaitech.com TXT
dig +short designhub._domainkey.image.sepaitech.com TXT
dig +short _dmarc.image.sepaitech.com TXT
dig +short -x 14.103.51.191
```

## 日常运维

查看服务状态和日志：

```bash
cd /opt/docker/design-hub
docker compose ps
docker compose logs --tail=100 smtp dkim api
```

查看邮件队列：

```bash
docker exec design-hub-smtp postqueue -p
```

强制重试暂时失败的邮件：

```bash
docker exec design-hub-smtp postqueue -f
```

查看指定队列项（正文包含密码重置验证码，仅限故障排查）：

```bash
docker exec design-hub-smtp postcat -q QUEUE_ID
```

邮件发送失败时，API 会让当前验证码立即失效；用户可以重新申请，不需要等待原验证码过期。应用日志只记录投递元数据，不记录验证码正文。

## 回滚

应用回滚使用部署前保留的 `design-hub-api` 镜像和数据库备份。邮件服务可独立停止：

```bash
cd /opt/docker/design-hub
docker compose stop smtp dkim
```

停止邮件服务后，生产环境保持 `MAIL_DELIVERY_MODE=smtp` 会让忘记密码请求明确失败，不会把验证码写入日志。不要切换到日志投递作为生产降级方案。

## 外部端口

云安全组仅需开放 22、80、443。SMTP 服务不需要入站 25；服务器只需要允许出站 TCP 25。3306、6379、8000、8891 均不得暴露公网。
