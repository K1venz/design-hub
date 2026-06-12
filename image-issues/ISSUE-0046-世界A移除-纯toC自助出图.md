---
id: ISSUE-0046
title: 世界 A 移除 — 客户/接单交付框架整体退役，实朴定性为纯 toC 自助出图
status: 已确认        # 用户已签字、实现棒开闸（#774）；非 bug，借状态机表「已确认=确认要做」
severity: P1          # 架构清理：化石框架占据 schema/代码/导航，与 toC 定性冲突
reporter: PM          # 用户拍板（#768/#774），coordinator 编排，PM 开条追踪
owner: 开发           # dev 第一棒（删码 + DROP 迁移 + openapi 再生），others 依赖
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
