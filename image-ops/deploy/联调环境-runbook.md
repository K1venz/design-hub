# listing 验收 · 联调环境 runbook（运维）

本轮 listing 一键出图验收，按「读类 / 写类」分两套环境，**绝不在 prod 上刷出图**。

## 一、读类 → prod 只读隧道（C 段回显复验 + 前端历史走查）

只读看 prod 既有历史数据（0031/0034/0016 回显），零成本零污染。

起隧道（同机同 key，无需 mount image-ops）：

```bash
API_IP=$(ssh -i ~/.ssh/dh_deploy_ed25519 root@203.0.113.10 \
  "docker inspect -f '{{(index .NetworkSettings.Networks \"design-hub_default\").IPAddress}}' design-hub-api")
ssh -i ~/.ssh/dh_deploy_ed25519 -N -L 8443:$API_IP:8000 root@203.0.113.10
```

或直接跑 `scripts/dev-tunnel.sh`（容器 IP 动态解析，重部署后仍可用）。

- 映射 `localhost:8443` → prod api 容器内 **uvicorn:8000**（绕 nginx）。
  映容器口而非 nginx 443：SSE 逐张事件不被缓冲、`?access_token=` query 不被截（ISSUE-0011）。
- 前端：`VITE_API_TARGET=http://localhost:8443`（纯 http、根路径，与 openapi.json 一致，无 /api 前缀、无自签证书）。
- 🔴 **只读铁律**：背后是真 prod DB + TOS + gpt 计费。只准 GET，**绝不 POST 出图**。

实测：经隧道 `/openapi.json`→200、`/listing/jobs`(无 token)→401、title="设计中台·图生图引擎 37 路由"。

## 二、写类 → 受控 :8002（A/B/D/E/F 出图链路）

本机起后端 :8002，独立非-prod MySQL + 真 gpt，**n 由请求体张数控**，守 60 张硬顶。

env override 口诀：**GPT 留 / TOS 清 / DB 换独立 MySQL**

```bash
DB_URL=mysql+aiomysql://dh_qa:<pwd>@127.0.0.1:3306/design_hub_qa?charset=utf8mb4  # 独立库，禁 SQLite(A4 真并发)
TOS_ACCESS_KEY=        # 清空！否则出图写 prod TOS 桶 = 污染 prod 存储
TOS_GENERATE_BUCKET=   # 清空
TOS_UPLOAD_BUCKET=     # 清空
# GPT_IMAGE_BASE_URL/API_KEY/MODEL 保留——本机 image-code/.env 已现成(apinebula.com/gpt-image-2)
JWT_SECRET=<≥32 字节随机串>
```

- 独立库由 `scripts/provision-qa-db.sh` 建（需本机 MySQL root 口令）。
- 首次空库：从 image-code/ 跑 `alembic upgrade head`（迁移链已烟测，建 15 张表）。
- ⚠️ TOS 少清 = 污染 prod 存储；用了 SQLite = A4 并发失真。两个都是验收事故。

## 三、prod 就绪度快照（只读核查）

| 项 | 状态 |
|---|---|
| 容器 | api healthy / nginx / mysql healthy |
| API | 37 路由、401 鉴权正常；nginx `proxy_buffering off` |
| TLS | 443 HTTP/2 200（自签 CN=design-hub.local，到 2028） |
| DB | mysql 容器 healthy + api healthcheck 绿 |
| TOS | cn-shanghai 端点 prod 出网可达，签名 url 现签在跑 |
| 外网 | 80→301 跳 https、443→200 可达；3306 外网 filtered（见 ISSUE-0036） |
