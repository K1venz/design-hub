# 手动部署 SOP / checklist

> **背景**：B-1②（安全加固）把 CI auto-deploy 改成 PR 门禁后，**部署全手动**——原本 CI 自动 `npm build` 前端、rsync dist 的步骤，现在变成人工常项。
> **0040 demo 实锤**：手搓 rsync 部署（只 rsync image-code + build api）漏了前端 dist → prod ship 了加固轮旧 bundle、`/edit` 路由不在、demo 暴露。本 checklist 把前端步骤结构化防再犯。

## 铁律
**永远走 `push.sh`，不要手搓 rsync。** push.sh 已无条件重建前端 dist + 推全部三件（code/deploy/dist），漏前端在结构上不可能。手搓 rsync = 漏前端的唯一来源。

## 标准部署序列
1. **回滚保险 + baseline 快照**
   `docker tag design-hub-api:latest design-hub-api:rollback-$(date +%Y%m%d-%H%M%S)`
   记 baseline：`app_user` 数 / `listing_job` 数 / `alembic_version`。
2. **推送（含前端构建）**：`bash image-ops/deploy/scripts/push.sh`
   = [1]无条件 build 前端 dist → [2]rsync image-code → [3]rsync image-ops/deploy → [4]rsync dist(--delete)。
3. **重建**：`ssh … 'cd /opt/docker/design-hub && bash scripts/deploy.sh'`
   = [6a]迁移前 mysqldump 备份 → build api → alembic upgrade head → up -d。
4. **nginx reload（仅当 nginx conf 有改动）**：
   `docker exec design-hub-nginx nginx -t && docker exec design-hub-nginx nginx -s reload`
   —— deploy.sh 的 `up -d` **不会**因挂载 conf 内容变化重建 nginx，必须显式 test-then-reload（零停机）。
5. **验证**
   - api `healthy`；新路由探针（无 auth POST → 401 = 路由在）。
   - **前端有改动**：prod `index.html` 引用的 bundle hash 已变 + 新 bundle `grep` 到新特征串；公网 `curl -sk https://203.0.113.10/ | grep index-*.js` 确认。
   - 公网 `https://203.0.113.10`：`/` 200；加固面 `/docs`·`/api/docs`·`/metrics` 仍 404（未被本次部署破坏）。
6. **收尾**：prod smoke 造的测试号/单/TOS 孤儿按纪律清（盘点先行 + children-first 事务删 + 保真实用户），baseline 复原。

## 常踩的坑（务必当常项核）
- **前端 dist**：B-1② 后前端 ship=手动。走 push.sh 则结构保证；手搓 rsync 必漏（见上）。
- **nginx reload**：conf 改了不 reload = 旧 conf 仍在内存生效。
- **迁移备份**：deploy.sh [6a] 已强制；破坏性迁移再核备份产物 bytes > 0。
- **回滚**：旧镜像 retag（步骤1）+ 迁移前全库备份（[6a]）= 双保险。
- **user_id 非 email**：清理见 [project_prod_db_userid_scheme]（listing/cost_ledger 等 user_id = app_user.id 字符串）。
