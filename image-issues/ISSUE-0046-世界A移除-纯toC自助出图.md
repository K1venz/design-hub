---
id: ISSUE-0046
title: 世界 A 移除 — 客户/接单交付框架整体退役，实朴定性为纯 toC 自助出图
status: 已关闭        # PM 终验收（2026-06-12）：QA 双网复核全绿 + ops prod 部署核验完毕，闭环
severity: P1          # 架构清理：化石框架占据 schema/代码/导航，与 toC 定性冲突
reporter: PM          # 用户拍板（#768/#774），coordinator 编排，PM 开条追踪
owner: PM             # 已关闭（PM 终验收 2026-06-12）
created: 2026-06-12
updated: 2026-06-12
related:
  - 设计稿: docs/superpowers/specs/2026-06-12-remove-world-a-toc-only-design.md
  - dev 蓝图（实现权威）: image-code/docs/世界A移除蓝图-dev调研.md（commit 56a2083，AST import 图谱 96 模块）
  - 前端调研: 群 #769/#772（frontend-b 整删/需改/必保三档清单）
  - PRD: §0 定性修订（2026-06-12）+ §2.3/§3.3/§3.11/§4 ❌ 废止标记
  - 群聊: image-gen#1 #768-#774（调研令→双调研→用户签字→实现棒）
---

## 定性（用户拍板 2026-06-12）
实朴 = **纯 toC 自助出图**：卖家与普通人是同一种用户——「上传自己的东西 → 给自己出图」，
**零第三方甲方、无接单交付关系**。原「设计中台」的客户/项目/需求单/改稿/交付框架
（「世界 A」）= 上一版定位的化石，**整体移除、不留品牌预设、不留兼容壳**。

## 用户签字记录（#774）
1. **DROP 8 表**（亲签，DB 铁律）：children-first 序
   `generated_image → generation_job → deliverable → revision → asset → brief → project → customer`。
   prod 老表全 0 行（ops #762 早期残留已清）= **零数据损失**。
   **部署时修正（2026-06-12）**：customer 实有 1 行（zhaokai 测试录入 APPLE/COOK，调研后新产生）——
   ops DROP 前 STOP-and-ask，**用户拍「删」**（随表删、已入带标签备份可恢复），前提修正后继续。
2. **成本看板案 A**：dashboard 链整删（旧 5 维聚合查 0 行老表 = 空壳）；
   **toC 成本看板**（按 listing 表 + cost_ledger 重设计）入 backlog，owner=PM。
3. **角色文案档 a**：UI 字面「设计师」→「用户」；`app_user.role` DB 枚举**不动**（改值=迁移=签字，字面收益不值）。

## 范围（实现权威 = dev 蓝图 56a2083）
- **后端（dev）**：世界 A 全套删码（dashboard 链 / 4 个零被引死 port / failover.py 等死文件 /
  枚举 11 删 3 保——SubScene/Tier/Family/Style/Category/Material/ProjectStatus/JobStatus/AssetKind/
  RevisionStatus/GenMode 删，ModelName/TaskEventType/Role 保）+ 8 表 DROP 迁移 + openapi 再生 +
  删世界 A 测试用例。注意：枚举 Category ≠ listing 的 category 字符串（"FOOD"+CategoryCardRegistry，已验零引）。
- **前端（frontend-b，dev 起步后接）**：整删 CustomersPage / CreateCustomerDialog（含「品牌色」=品牌预设前端面）/
  api/customers.ts / /customers 路由 + nav「客户」/ DashboardPage + api/dashboard.ts + CostCharts + KpiCard +
  nav「业务仪表盘」/ PagePlaceholder（死文件）；注册页「设计师」文案→「用户」；codegen 重拉（等 dev openapi）。
  **RoleRoute 保**（admin/models、admin/users 仍用）。
- **保留不碰（铁律）**：model_config / cost_ledger / app_user / listing×3 六表、
  provider `generate()`（已是 toC-only 签名、listing 调用面 100% 此形状）、guard 预扣链（仅 1 行注释改）。
- **STOP 条款**：任何缠绕点不能 trivial 移除 → 立即停手报 coordinator，不硬拆。

## 验收标准（QA，dev+fe 完工后）
1. listing / uploads / auth / 出图全链**零变化**（回归绿）。
2. `/customers`、`/dashboard` 前后端均 404/不存在。
3. 8 表已 DROP、6 张保留表完好、cost_ledger + listing 数据完整（zhaokai 全量不动）。
4. 后端 tests 全绿（世界 A 用例已删、门禁数字随之更新）。

## 部署（ops，QA 绿后）
先 mysqldump 备份（可回滚）→ DROP 迁移 → deploy.sh（api）+ push.sh（前端 dist）双份 →
prod smoke（登录→出图→计费正常、管理后台无死链）。

## 处理记录
- 2026-06-12 [PM] 用户拍板定性（#768）→ coordinator 派只读双调研：dev AST 图谱蓝图（56a2083，
  四个高危缠绕点全排除：①老表活链零读写 ②cost_ledger 结构性零世界A维度、dashboard=查 0 行老表的空壳
  ③provider 端口已是 toC-only 零风险 ④枚举 11 删 3 保）+ frontend 三档清单（#769/#772，前端零 STOP 缠绕）。
  用户签字：8 表 DROP + 看板案 A + 角色文案档 a（#774）→ 实现棒开闸。PM 开本条 + PRD 落定性修订
  （§0 + §2.3/§3.3/§3.11/§4 ❌ 废止标记 + §3.12.12 客户档案保留句修订 + toC 成本看板 backlog）。
  owner=开发（第一棒删码+迁移），流转：dev → frontend-b → QA 回归 → ops 部署 → PM 验收关闭。
- 2026-06-12 [开发] dev 棒完成（commit cdb6be0，47 文件 +56/−2650）：整删 36 文件（14 死模块闭包
  + customers 链 + dashboard 链案 A）；enums 11 删 3 保、域模型 15 删 7 保、ORM 8 删 6 保；
  迁移 a1f7c3d9e5b2 DROP 8 表 children-first（downgrade=NotImplementedError，回滚走备份），
  临时库从零 upgrade head 实跑验证终态恰 6 表 ✓；openapi 再生 18→15 paths（customers/dashboard
  消失）；门禁 ruff ✅ + pytest 49 绿（tests 零受影响、无世界A测试可删——验收第 4 条"门禁数字
  随之更新"实际数字不变=49）；6 保留表/provider generate()/guard 预扣链零触碰。状态→实现中，
  接力 frontend-b（codegen 重拉）+ QA（4-prong gate）。
- 2026-06-12 [前端] frontend-b 棒完成（两笔）：① 3702483 整删 8 文件 −1087 行（CustomersPage/
  CreateCustomerDialog[含品牌色输入=品牌预设前端面]/api customers+dashboard/案A看板四件套/
  PagePlaceholder）+ /customers·/dashboard 路由与导航摘除（RoleRoute 保，admin 两页仍用）+
  注册页档 a 文案（DB 枚举零动）+ npm uninstall recharts；② a2ce62a openapi 重拉 −906 行，
  世界A codegen 类型 0 残留、listing 契约完好实证。门禁 eslint/tsc/vitest 25 绿 + build ✅
  （tsc 绿=删除闭包机器证明）。接力 QA 4-prong gate。
- 2026-06-12 [QA] **4-prong gate 全绿**（验收①②③④）：
  ① **listing/uploads/auth/出图全链零变化** ✅（`world_a_removal_regression.py` 跑 qa 8444、ops 重建后）：
     auth(register/login/me)+uploads + 单图流 n=1(完成/1张/cost reconcile) + 套图 plan 1/1/1(完成/
     分布1/1/1/cost reconcile) + history 全 PASS——删世界 A 未误伤 listing 共享依赖。
  ② **/customers·/dashboard → 404** ✅ + **保留路由反向核**（/admin/users 403·/admin/models 403·
     /listing/jobs 200 = 非404 仍挂载）= 选择性删除没误删活路由。
  ③ **DB schema** ✅（核 ops #787 SHOW TABLES BEFORE15→AFTER7）：8 表 children-first 全 DROP、
     6 保留表(model_config/cost_ledger/app_user/listing×3)完好、alembic→a1f7c3d9e5b2(head)。
     QA 无 dh_qa_ro 凭证、核 ops output（manifest 见 `world_a_db_check.py`）。
  ④ **后端 pytest 49 绿** ✅（本地 c4a3ef3 实跑 `49 passed`，验 dev「门禁数字不变=49」）。
  **honest**：①② 首跑 13/15，2 红经核**全是我预写脚本探测 bug、非回归**——MeResponse 字段=user_id/
  name/role/dept（无 email、我误断 email）、users 路由在 `/admin/users`（prefix=/admin、我误探裸 /users）；
  读代码+活探（/me 401、/admin/users 401）坐实路由/字段无恙，**修正为正确断言**（非削弱让其假绿）后重跑 15/15。
  gate 脚本 8d4d1ee + 本笔修正提交。→ **QA 验收全绿、放行**，owner 交 coordinator（放行 ops 部署）。
- 2026-06-12 [运维] **ops 末棒部署完成、核验全绿**：带标签备份 prod
  (`prod-db-backup-worldA-20260612-211427.sql` 21450B)+**test-restore 验证 restorable** → push.sh(世界A前端整删、
  新 bundle BpWigf8b、dashboard chunk 消失、recharts 卸载) → deploy.sh(api build + 迁移 e4a9b2c61f73→a1f7c3d9e5b2
  DROP 8 表 children-first) → prod smoke 全绿：**SHOW TABLES 15→7**(8 世界A DROP / 6 保留+alembic head a1f7c3d9e5b2)、
  **zhaokai TOC 数据逐项不变**(app_user3/listing_job3/listing_image13/cost_ledger5/model_config4)、customer 表 doesn't exist、
  公网世界A路由 404·listing/admin 活·加固(docs 404)持续。
  **DROP 前 STOP-and-ask**：审计发现 customer 表非 0 行（zhaokai 的 APPLE/COOK 测试录入，dev 蓝图「0 行零损失」对此已不成立）
  → 报 coordinator → 用户拍「删」（随表删、已在备份可恢复）。三重回滚保险（显式备份 + [6a] 备份 + api 旧镜像 rollback-20260612-211822）。
  → 待 QA 公网复核 + PM 验收关闭。
- 2026-06-12 [QA] **prod 公网复核 15/15 全绿**（coordinator #789 双保险收口）：公网 `https://203.0.113.10`（/api 前缀）
  跑 world_a_removal_regression.py——① listing/uploads/auth/出图全链**零变化**（单图 cost0.40 + 套图 plan1/1/1 cost1.20
  + auth/me/uploads/history 全 PASS）② `/api/customers`·`/api/dashboard` **404** + 保留路由反向核（`/api/admin/users`·
  `/api/admin/models` 403、`/api/listing/jobs` 200 = 仍挂载）。**ops prod smoke + QA 公网复核双网皆绿**。
  脚本泛化 /api 前缀提交 56b8c67。footprint（qa-worlda-* 测试号 + 2 jobs + 4 图 + ¥1.60 + TOS）交 ops 清、保 zhaokai。
  → **QA 验收①②③④ 全部闭环、无遗留异议**，@pm 终验收关闭。
- 2026-06-12 [PM] **终验收通过 → 关闭**。对验收标准逐条核：① listing/uploads/auth/出图全链零变化——
  **双网实证**（qa 8444 gate ① + prod 公网复核 15/15，单图 cost0.40/套图 plan1/1/1 cost1.20 计费正常）；
  ② /customers·/dashboard 双网 404 + 保留路由反向核（admin 两页/listing 仍挂载=选择性删除无误删）；
  ③ SHOW TABLES 15→7（8 表 children-first 全 DROP、6 保留表完好、alembic head a1f7c3d9e5b2）+
  **zhaokai toC 数据逐项不变**（listing_job 3/listing_image 13/cost_ledger 5/model_config 4）；
  ④ pytest 49 绿（tests 零受影响，验收第 4 条字面「门禁数字更新」按 dev 实况修正=数字不变）。
  过程纪律三亮点入档：ops **STOP-and-ask**（签字前提变更即停、用户拍删后续跑）+ 三重回滚保险
  （带标签备份 test-restore 验证 + [6a] 备份 + 旧镜像）+ QA honest 自纠（探测脚本 bug 修正为正确断言、
  非削弱假绿）。PRD §0 定性修订补 ✅ 已落地标记。遗留：QA prod footprint 由 ops 清（不阻关闭）；
  toC 成本看板 backlog（owner=PM，拟与 §7.D 积分制同轮）。**status→已关闭**。
