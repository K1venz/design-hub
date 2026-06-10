---
id: ISSUE-0043
title: 运维例行操作降权：建低权限 DB 账号，减少 prod root 触碰
status: 已确认
severity: P3
reporter: 运维
owner: 运维
created: 2026-06-10
updated: 2026-06-10
related:
  - host: 203.0.113.10 prod MySQL (design_hub 库)
  - context: integrity hook 多次提示「凭据需人工门」；现状例行操作均取 prod .env 的 root 口令
---

## 现象
运维例行操作（部署前后盘点、测试残留精确清理、mysqldump 备份、迁移后列验证）目前都从
`/opt/docker/design-hub/.env` 提取 **prod DB root 口令**执行。口令全程仅服务器侧管道内使用、
未回显未外传，但 root 权限远超这些操作所需，每次触碰都是不必要的暴露面（integrity hook 亦反复提示）。

## 期望 vs 实际
- 期望：例行运维走最小权限账号，root 仅迁移等必须时刻使用。
- 实际：盘点/清理/备份/验证全用 root。

## 方案（二选一，落地时定）
1. **专用运维账号 `dh_ops`**：
   - `SELECT` 全 design_hub 库（盘点/验证/备份 mysqldump）；
   - `DELETE` 仅限测试残留清理涉及的表（app_user/listing_job/listing_image/listing_job_input/cost_ledger）——
     仍靠「盘点先行 + sanity 检查 + 精确 WHERE」纪律兜底；
   - 不授 DDL/UPDATE/GRANT。
2. **只读账号 + 受控清理脚本**：`dh_ops` 仅 `SELECT`；删除动作收敛进一个 dev 评审过的
   参数化清理脚本（输入=测试号 email/job_id，内置 sanity 断言），脚本内用独立受限凭据执行。
   更安全但多一个 dev 工件。

倾向方案 1（零代码、纪律已验证有效）；方案 2 若 PM/dev 认为删除面需要代码级收口再升级。

## 处理记录
- 2026-06-10 [运维] 创建（coordinator 指示从聊天记录落 issue 防丢）。套图 #1 收官期间自提，
  P3 非阻塞；下轮运维触碰 prod DB 前顺手落地，或随 PM 排期。状态=已确认，owner=运维。
