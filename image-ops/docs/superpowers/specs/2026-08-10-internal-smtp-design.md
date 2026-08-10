# Design Hub 内部 SMTP 投递服务技术设计

日期：2026-08-10  
状态：已批准，待实施  
适用环境：`14.103.51.191` 上的 `/opt/docker/design-hub`

## 1. 目标

在现有 Design Hub Docker Compose 栈内增加一套仅供应用使用的出站邮件服务，为忘记密码验证码提供真实邮件投递能力。

发件身份固定为：

- 邮件地址：`no-reply@image.sepaitech.com`
- SMTP/HELO 主机名：`smtp.image.sepaitech.com`
- 公网 IPv4：`14.103.51.191`
- DKIM selector：`designhub`

系统必须满足以下结果：

1. API 通过 Docker 私有网络提交邮件，不连接第三方 SMTP 服务。
2. Postfix 直接向收件方 MX 投递，OpenDKIM 对出站邮件签名。
3. SMTP 接收端口不映射到宿主机公网。
4. 仅允许 Design Hub Docker 网络内的应用提交邮件，不形成开放中继。
5. 邮件队列和 DKIM 私钥持久化，容器重建不丢失。
6. 生产环境缺少 SMTP 配置时启动失败，不再把验证码明文写入日志。

## 2. 非目标

本期不建设完整邮箱系统，不提供 IMAP、POP3、Webmail、用户邮箱、垃圾邮件收件或公网 SMTP Submission。本期也不接入外部邮件服务商作为上游中继。

退信由 Postfix 队列与日志记录，不建设退信解析、用户级投递统计或自动封禁系统。

## 3. 现状与约束

### 3.1 应用现状

后端已经实现 `SmtpMailer`，支持普通 SMTP、STARTTLS 和可选用户名密码。生产组装逻辑在 `image-code/src/design_hub/interface/api/asgi.py` 中根据 `SMTP_HOST` 与 `SMTP_FROM` 选择 SMTP 或日志邮件器。

现有部署的 `.env` 没有任何 `SMTP_*` 设置，因此忘记密码请求当前只把验证码写入 API 日志。

### 3.2 服务器现状

- Ubuntu 24.04，约 3.8 GiB 内存；检查时约 2.0 GiB 可用。
- 根分区剩余约 2.9 GiB，`/data` 剩余约 37 GiB。
- Docker Compose 项目网络为 `design-hub_default`。
- 公网出站 TCP/25 已实测可达。
- 宿主机当前没有监听 25、465 或 587 端口。

### 3.3 DNS 现状

- `image.sepaitech.com A 14.103.51.191` 已存在。
- `image.sepaitech.com` 当前没有 SPF、MX 或子域 DMARC 记录。
- 父域存在 `_dmarc.sepaitech.com TXT "v=DMARC1; p=none;"`。
- `14.103.51.191` 当前没有有效 PTR。

SMTP 服务可以在 DNS 完成前启动和通过内部验收，但不得把“外部投递可用”判定为完成，直到 SPF、DKIM、DMARC 与 PTR 全部验证通过。

## 4. 方案选择

### 4.1 采用方案：Postfix + OpenDKIM 直接投递

部署两个职责独立的容器：

- `smtp`：运行 Postfix，接收 API 提交、管理持久化队列并直接投递到收件方 MX。
- `dkim`：运行 OpenDKIM，仅向 `smtp` 提供 milter 签名服务。

两个容器都从 Debian stable slim 构建，只安装发行版提供的 Postfix、OpenDKIM、证书和必要运行工具。不引入完整邮件套件或来源不明的预制邮件服务器镜像。

### 4.2 未采用方案

1. **本地 Postfix 中继到外部服务商**：到达率较高，但不符合完全自建要求。
2. **Mailcow/Mailu 完整套件**：包含本项目不需要的收件箱、反垃圾与 Webmail，占用资源和运维面过大。
3. **API 直接连接收件方 MX**：应用会承担 DNS、重试、队列、退避和投递状态管理，破坏现有邮件端口边界。

## 5. 架构

```text
Forgot password API
       |
       | SMTP, Docker private network, port 25
       v
Postfix smtp container ------ TCP 8891 ------> OpenDKIM container
       |                                           |
       | persistent queue                          | persistent private key
       v                                           v
/data/docker/design-hub/mail/spool       /data/docker/design-hub/mail/dkim
       |
       | DNS MX lookup + opportunistic outbound TLS
       v
Recipient mail server
```

`smtp` 和 `dkim` 加入独立的 Compose `mail` 内部网络。API 同时加入现有默认网络和 `mail` 网络。Worker 与 nginx 不加入 `mail` 网络，因为它们不需要提交邮件。

`mail` 网络设置 `internal: true` 会阻止 Postfix访问公网，因此不能使用。该网络不发布任何宿主机端口，并通过 Postfix 的 `mynetworks` 与 relay restrictions 限制提交来源。

## 6. 容器与文件边界

新增目录：

```text
image-ops/deploy/mail/
├── postfix/
│   ├── Dockerfile
│   ├── entrypoint.sh
│   └── main.cf.template
└── opendkim/
    ├── Dockerfile
    ├── entrypoint.sh
    └── opendkim.conf
```

职责如下：

- Postfix `entrypoint.sh` 校验必需环境变量，渲染配置，检查 `postfix check`，然后以前台模式启动 Postfix。
- OpenDKIM `entrypoint.sh` 校验挂载的私钥、权限和配置，然后以前台模式启动 OpenDKIM。
- DKIM 密钥由部署脚本首次生成。已有密钥时必须复用，禁止静默覆盖。
- 部署脚本把 DNS 所需公钥写入服务器 root-only 文件，不在普通部署日志中输出私钥。

持久化路径：

```text
/data/docker/design-hub/mail/spool
/data/docker/design-hub/mail/dkim
/data/docker/design-hub/mail/dns-records.txt
```

## 7. Postfix 安全配置

Postfix 使用以下边界：

- `myhostname = smtp.image.sepaitech.com`
- `myorigin = image.sepaitech.com`
- `inet_interfaces = all`，但容器端口仅 `expose`，不设置宿主机 `ports`。
- `mynetworks` 只包含容器 loopback 与部署时明确传入的 `design-hub_mail` 子网。
- `smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination`
- `smtpd_recipient_restrictions = permit_mynetworks, reject_unauth_destination`
- `smtpd_client_restrictions = permit_mynetworks, reject`
- 不启用 SMTP AUTH；Docker 网络隔离承担应用到 MTA 的访问边界。
- `smtpd_milters` 与 `non_smtpd_milters` 指向 `inet:dkim:8891`。
- milter 不可用时临时失败邮件提交，避免发送未签名验证码；不静默绕过 DKIM。
- 出站 SMTP 使用机会式 TLS，并加载系统 CA。直接投递采用 `may` 语义：远端支持 TLS 时加密并记录证书验证结果，远端不支持时仍允许投递，避免把不支持 TLS 的合法 MX 全部阻断。
- 限制单封邮件大小、单连接收件人数和并发，防止应用异常扩大影响。
- Postfix 日志只记录信封、队列 ID 和投递状态，不记录验证码正文。

开放中继验收必须从不在 `mynetworks` 的临时容器发起，并确认远端收件人被拒绝。仅验证“公网没有映射 25 端口”不能替代 relay policy 测试。

Postfix 官方文档将 `smtpd_relay_restrictions = permit_mynetworks, reject_unauth_destination` 作为现代版本的中继控制边界；配置顺序不可改变：<https://www.postfix.org/SMTPD_ACCESS_README.html>。

## 8. DKIM 设计

- 算法：RSA 2048。
- 签名域：`image.sepaitech.com`。
- selector：`designhub`。
- 私钥路径：`/data/docker/design-hub/mail/dkim/designhub.private`。
- 公钥记录：`designhub._domainkey.image.sepaitech.com`。
- 私钥只允许 root 和 DKIM 容器运行用户读取，禁止进入 Git、镜像层或命令输出。
- OpenDKIM 只对来自 Postfix 且发件域匹配 `image.sepaitech.com` 的邮件签名。
- 容器健康检查同时检查 OpenDKIM 进程和 8891 监听端口。

OpenDKIM 作为 Postfix milter 的连接方式遵循 Debian OpenDKIM 文档：<https://wiki.debian.org/opendkim>。

## 9. 应用配置

生产 `.env` 增加：

```dotenv
SMTP_HOST=smtp
SMTP_PORT=25
SMTP_USERNAME=
SMTP_PASSWORD=
SMTP_FROM=no-reply@image.sepaitech.com
SMTP_USE_TLS=false
MAIL_DELIVERY_MODE=smtp
PASSWORD_RESET_CODE_PEPPER=__GENERATED_64_HEX__
```

容器内 SMTP 不启用 TLS，因为链路只存在于未发布端口的 Docker 网络。Postfix 到公网收件服务器的 TLS 由 Postfix 独立管理。

应用配置增加显式 `MAIL_DELIVERY_MODE`：值只能是 `smtp` 或 `log`。`smtp` 模式若缺少 `SMTP_HOST`、`SMTP_FROM` 或重置码 pepper，启动立即失败；服务器 `.env` 固定使用 `smtp`。`LoggingMailer` 只允许本地开发与测试显式选择 `log`，且日志内容不得包含验证码正文。

重置码 pepper 与 JWT secret 分离，新增独立的 `PASSWORD_RESET_CODE_PEPPER`，由部署脚本生成并保存到 `.env`。

## 10. DNS 与云平台配置

部署生成 DKIM 公钥后，需要添加以下记录：

```dns
smtp.image.sepaitech.com.                 A     14.103.51.191
image.sepaitech.com.                      TXT   "v=spf1 ip4:14.103.51.191 -all"
designhub._domainkey.image.sepaitech.com. TXT   部署产物 dns-records.txt 中的完整 DKIM TXT 值
_dmarc.image.sepaitech.com.               TXT   "v=DMARC1; p=none"
```

火山引擎公网 IP 反向解析设置为：

```text
14.103.51.191 PTR smtp.image.sepaitech.com
```

正向和反向必须一致：`smtp.image.sepaitech.com` 解析到 `14.103.51.191`，该 IP 的 PTR 再返回 `smtp.image.sepaitech.com`。

首期 DMARC 使用 `p=none` 收集投递情况。真实投递稳定且 SPF/DKIM 对齐后，再单独评审升级到 `quarantine` 或 `reject`；本次部署不自动提高策略。

## 11. 邮件数据流与失败处理

1. 用户请求忘记密码。
2. API 生成并持久化验证码挑战。
3. API 向 `smtp:25` 提交纯文本邮件。
4. Postfix 接受邮件前通过 OpenDKIM milter 完成签名。
5. Postfix 返回 SMTP 2xx 后，API 才向用户返回统一成功文案。
6. Postfix 根据目标域 MX 投递；临时错误进入持久化队列，永久错误记录为 bounced。

API 无法连接 SMTP 或 SMTP 拒绝提交时，接口返回服务错误。应用必须使本次新验证码失效，避免用户收到失败响应后仍被冷却时间阻塞。该失效动作只处理本次新建挑战，不影响此前已经成功发送的挑战。

Postfix 已接受但后续远端投递失败时，API 无法同步知道最终结果；由队列、日志和监控反映。这是 SMTP 存储转发协议的正常边界。

## 12. 部署流程

1. 备份 `/opt/docker/design-hub/.env`、当前 Compose 配置和 API 镜像标签。
2. 创建 `/data/docker/design-hub/mail/{spool,dkim}` 并设置最小权限。
3. 首次生成 DKIM RSA 2048 密钥；存在即复用。
4. 构建 `smtp`、`dkim` 和更新后的 API 镜像。
5. 使用 `docker compose config` 验证配置。
6. 只启动 `dkim` 和 `smtp`，等待健康检查通过。
7. 从 API 网络进行 SMTP 提交测试并检查 DKIM-Signature。
8. 更新生产 `.env`，启动 API，执行数据库迁移和现有健康检查。
9. 完成 DNS/PTR 后，向至少两个不同邮件服务商的真实邮箱发送测试邮件。
10. 验证 SPF、DKIM、DMARC 对齐和邮件正文中的验证码。

部署脚本必须幂等：重复执行不重建 DKIM 私钥、不清空邮件队列、不覆盖已有非空 SMTP 配置。

## 13. 健康检查与监控

### 13.1 容器健康

- `dkim`：进程存在且 8891 端口监听。
- `smtp`：`postfix status` 正常，并可在容器内完成 SMTP banner/EHLO 检查。
- API：沿用现有 `/metrics` 健康检查，并增加启动期 SMTP 配置校验。

### 13.2 运行观测

至少观测以下指标或日志事件：

- Postfix active/deferred 队列长度。
- `status=sent`、`status=deferred`、`status=bounced` 数量。
- DKIM milter 不可达或签名失败。
- API 到 SMTP 的连接错误和提交错误。

日志中禁止记录 SMTP 密码、DKIM 私钥、验证码正文和完整的重置码 hash。

## 14. 验收标准

### 14.1 本地与配置验收

- `docker compose config` 成功。
- Postfix 与 OpenDKIM 配置静态检查成功。
- DKIM 私钥未被 Git 跟踪，容器重建后 fingerprint 不变。
- 生产配置缺失时应用启动失败；开发配置可显式使用安全日志邮件器。

### 14.2 服务器内部验收

- `smtp`、`dkim`、`api`、`worker`、`nginx`、`redis` 全部健康。
- 宿主机公网没有监听 25、465、587。
- API 容器能向 `smtp:25` 提交邮件。
- 非授权容器不能通过 SMTP 向外部域中继。
- Postfix 队列目录和 DKIM 私钥位于 `/data` 持久卷。

### 14.3 外部投递验收

- A、SPF、DKIM、DMARC、PTR 查询结果正确。
- 至少两个不同服务商的测试邮箱收到验证码邮件。
- 邮件头显示 SPF pass、DKIM pass、DMARC pass。
- 忘记密码端到端流程能够使用收到的验证码设置新密码。
- SMTP 暂停时接口明确失败，新验证码不会造成重发冷却阻塞。

## 15. 回滚

1. 停止 API 写入 SMTP，恢复部署前 `.env` 和 API 镜像。
2. 恢复部署前 Compose 文件并启动原服务集合。
3. 保留 `/data/docker/design-hub/mail`，避免误删队列和 DKIM 身份；确认不再需要后再单独清理。
4. SMTP DNS 记录可保留以便修复后复用；若确认永久撤回，先删除 SPF/DKIM/SMTP A 记录，再申请移除 PTR。

回滚不得删除数据库迁移、用户账号或现有 Design Hub 业务数据。

## 16. 实施范围

本设计对应一个实施计划，包含以下闭环：

1. 增加 Postfix/OpenDKIM 容器与持久化配置。
2. 扩展生产环境变量、部署脚本和运维说明。
3. 收紧生产邮件器配置并拆分重置码 pepper。
4. 处理 SMTP 提交失败后的挑战失效。
5. 增加基础设施与应用测试。
6. 在服务器部署、验证内部 SMTP、生成 DNS 记录。
7. DNS/PTR 生效后完成真实邮件端到端验收。
