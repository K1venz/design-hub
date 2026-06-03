# design-hub 部署（运维）

首发形态：**前端 SPA(image-web/dist) + API(FastAPI/uvicorn) + 复用现有 MySQL 8.4 + nginx/TLS 反代**。
nginx 静态托管前端、`/api/*` 去前缀转发后端；`/docs`、`/metrics` 直达后端。
监控（Prometheus/Grafana）、备份、CI/CD 暂未做（首发范围决策见下）。

## 目标服务器
- `203.0.113.10`（Ubuntu 24.04，2C/3.8G，docker 数据盘 `/data` 37G 可用）
- 现有 MySQL 8.4 跑在 docker（compose `/opt/docker/mysql`，网络 `mysql_default`，数据 `/data/docker/mysql`）

## 部署决策（用户拍板）
1. 范围：贴 PRD 但首发只到 nginx+TLS；监控、备份先不做
2. DB：新建 `design_hub` 库，应用用 **root** 连
3. 密钥：provider 出图密钥先留空（出图暂不可用），JWT 服务器本地生成
4. 上线：rsync 源码 → 服务器本地构建（仓库暂无 git remote，等价替代 git-clone 构建）

## 服务器目录布局
```
/opt/docker/design-hub/
├── compose.yml                  # api + nginx
├── .env                         # 部署时生成，gitignored，不入库（含 DB_URL/JWT/seed 管理员）
├── app/                         # rsync 的 image-code 源码 = 构建上下文
│   ├── Dockerfile
│   └── .dockerignore
├── nginx/
│   ├── conf.d/design-hub.conf
│   └── certs/                   # 自签证书（deploy.sh 生成）
└── scripts/deploy.sh
/data/docker/design-hub/{generated,assets,exports}   # 持久卷
```

## 网络与连库
- api 容器接入两张网：项目网（与 nginx 通）+ 外部 `mysql_default`
- 连库 host = `mysql:3306`（现有容器名/别名），DB_URL 走 aiomysql

## 推送 + 部署
本地推送（源码 + 部署产物 + 前端 dist；自动保护服务器 .env/certs/web）：
```bash
bash image-ops/deploy/scripts/push.sh        # 可用 DEPLOY_KEY/DEPLOY_HOST 覆盖
```
再在服务器上重建（幂等）：
```bash
cd /opt/docker/design-hub && bash scripts/deploy.sh
```
> 注意：源码 rsync 用 `--delete` 时务必排除 `Dockerfile`/`.dockerignore`（它们来自 image-ops，不在 image-code 源码里），否则会被删导致 build 失败——push.sh 已处理。
脚本幂等：建目录 → 自签证书 → 生成 .env（已存在则保留）→ 建库 → 构建 → 迁移建表 → up → 健康检查。
迁移先于应用启动（应用 lifespan 会 seed 默认模型+管理员，需先有表）。

## 访问
- `https://203.0.113.10/`（前端 UI；自签证书，浏览器会告警；有域名可换 Let's Encrypt）
- `https://203.0.113.10/docs`（后端接口文档 Swagger）
- 云安全组需放行 **22 + 80 + 443**（22 限管理 IP；编辑安全组时勿覆盖掉 22）；3306/8000 不要对外暴露

## 更新前端
前端构建产物来自 image-web（独立构建），rsync 到 `web/` 后 nginx 直接生效（静态文件，无需重启）：
```bash
rsync -az --delete image-web/dist/ root@203.0.113.10:/opt/docker/design-hub/web/
```

## 已知问题
- [ISSUE-0018] aiomysql 缺 `cryptography`，MySQL 重启后冷启动连库会失败（当前靠缓存热可跑）。
  修复 owner=开发：`uv add cryptography`，镜像重建即生效。

## 后续（未做）
- Prometheus + Grafana（应用已内置 `/metrics`）
- 备份策略（MySQL 定时 dump）
- CI/CD（git remote 就绪后接 GitHub Actions）
- provider 出图密钥补齐后重启 api 开启出图
