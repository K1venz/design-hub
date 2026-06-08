# listing 验收 · 联调环境 runbook（运维）

listing 一键出图验收按「读类 / 写类」分两套，**绝不在 prod 库/桶上刷出图**。
用户拍板：写类验收在**服务器(14.103.51.191)上跑、图走真 TOS**（高保真，0034 过期可真复现），
但用**独立 qa 库 + 独立 qa 桶**与 prod 物理隔离。

## 一、读类 → prod 只读隧道（看 prod 既有数据）

> 注：本轮 prod listing 历史为空（listing_job=0），C 段回显复验改在 server qa 用 fresh 数据验；
> 此隧道仅用于「prod 现有记录不裂图」的附加快照。

```bash
API_IP=$(ssh -i ~/.ssh/dh_deploy_ed25519 root@14.103.51.191 \
  "docker inspect -f '{{(index .NetworkSettings.Networks \"design-hub_default\").IPAddress}}' design-hub-api")
ssh -i ~/.ssh/dh_deploy_ed25519 -N -L 8443:$API_IP:8000 root@14.103.51.191
```
或 `scripts/dev-tunnel.sh`。映容器 uvicorn:8000（绕 nginx：SSE 不缓冲、`?access_token=` 不被截）。
前端 `VITE_API_TARGET=http://localhost:8443`。🔴 只读，绝不 POST。

## 二、写类 → 服务器 qa 实例（A–F 全量，真 TOS）

服务器上一套与 prod 物理隔离的 qa：独立库 `design_hub_qa` + 独立 2 个 qa TOS 桶 + 独立 qa 容器。

**双轴隔离 + env 口诀（GPT 留 / TOS 配 qa 桶+短TTL / DB=独立库 / JWT）**
```
DB_URL=mysql+aiomysql://dh_qa:<pwd>@mysql:3306/design_hub_qa?charset=utf8mb4   # 独立库,非 prod
GPT_IMAGE_BASE_URL/API_KEY/MODEL   # 保留(同 prod .env 现成真密钥)
TOS_ACCESS_KEY/SECRET_KEY/REGION/ENDPOINT  # 保留(同 TOS 账号)
TOS_GENERATE_BUCKET=bucket-design-hub-qa-generate   # 独立 qa 桶,非 prod 桶
TOS_UPLOAD_BUCKET=bucket-design-hub-qa-upload        # 独立 qa 桶
TOS_SIGNED_URL_TTL=10              # 短 TTL → 0034 过期真复现
JWT_SECRET=<新随机 ≥32 字节>
```
> ⚠️ app 无 key 前缀配置（tos.py 按 sha-key 存桶根），TOS 隔离只能靠**独立桶**，不能靠前缀（前缀要改 image-code，本轮不做）。

**bringup（ops 用 server root 执行，约 10 分钟）**
1. 建库+账号：`CREATE DATABASE design_hub_qa` + `dh_qa`@%(全权) + `dh_qa_ro`@%(SELECT)。
2. 建 2 个 qa 桶：api 容器内 `tos` SDK `create_bucket`（同账号）。
3. 装配 qa.env：`cp prod .env` 再覆盖上面口诀的键（密钥全程留服务器，chmod 600）。
4. 取源 build：本机最新 main 未 push → `rsync image-code/ → /opt/docker/design-hub-qa/app/`（排除 .env/.git/.venv/db/产物），复用 prod Dockerfile（`image-ops/deploy/app/Dockerfile`），`docker build -t design-hub-qa-api:local`。
5. 迁移：`docker run --rm --env-file qa.env --network mysql_default design-hub-qa-api:local alembic upgrade head`（15 表）。
6. 起容器：`docker run -d --name design-hub-qa-api --env-file qa.env --network mysql_default -v /data/docker/design-hub-qa/{generated,assets,exports}:/app/... design-hub-qa-api:local`。
7. 隧道给团队：`ssh -N -L 8444:<qa容器IP>:8000 -L 13306:127.0.0.1:3306 root@server`。
   - 应用 `http://localhost:8444`（QA_BASE / VITE_API_TARGET）；只读 DB `localhost:13306`（dh_qa_ro）。
   - 凭据交接走服务器 root-only `/root/qa-handoff.txt`（SSH cat 取，**不进群聊**）。

**坑**
- 注册邮箱别用 `@*.local`/`@*.test`（保留 TLD 被 email-validator 拒 422）→ 用真实 TLD。
- `docker exec` 跑 heredoc 脚本要带 `-i`，否则 stdin 不进容器。
- qa.env 从 prod .env 拷来会带 `SEED_ADMIN_*` → qa 启动自动 seed 一个 manager（D 段 designer-only 一般用不上）。

**teardown（验收完销毁，零残留）**
```bash
docker rm -f design-hub-qa-api
docker exec mysql mysql -uroot -p<root> -e "DROP DATABASE design_hub_qa; DROP USER 'dh_qa'@'%','dh_qa_ro'@'%';"
# qa 桶清空+删: api 容器内 tos SDK delete_object 全量后 delete_bucket(qa 两个桶)
rm -rf /opt/docker/design-hub-qa /data/docker/design-hub-qa /root/qa-handoff.txt
docker rmi design-hub-qa-api:local
```

## 三、prod 就绪度快照（只读核查）

| 项 | 状态 |
|---|---|
| 容器 | api healthy / nginx / mysql healthy |
| API | 37 路由、401 鉴权正常；nginx `proxy_buffering off` |
| TLS | 443 HTTP/2 200（自签 CN=design-hub.local，到 2028） |
| DB | mysql 容器 healthy；prod `design_hub` 库 listing 历史=0 |
| TOS | cn-shanghai；prod 桶 generate/upload；qa 桶 qa-generate/qa-upload（并存隔离） |
| 外网 | 80→301、443→200 可达；3306 外网 filtered（见 ISSUE-0036） |
