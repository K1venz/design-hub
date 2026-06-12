# 移除「世界 A」：实朴回归纯 toC 自助出图 — 设计稿

- 日期：2026-06-12
- 状态：用户已拍板（批准删 8 表 + 成本看板案 A + 角色文案档 a）
- 决策依据：dev AST 全仓导入图谱蓝图（`image-code/docs/世界A移除蓝图-dev调研.md`，commit 56a2083）+ frontend-b 前端面调研

## 一、背景与产品定性

实朴 = **纯 toC 自助出图工具**。用户（电商卖家 + 普通人）做的事本质一致：

> 上传我自己的东西 → AI 给我出图 → 图归我自己用。

没有第三方甲方。卖家不是在替别人做设计，普通人更不是；两边「出图的人 / 使用的人 / 受益的人」是同一个人。**卖家 vs 普通人 = 市场细分（落地页/默认模板/计费档），不是关系差异**——一条 `user_id` 主线即可承载。

「设计师服务客户、客户名下建项目交付」这套是上一版「设计中台」形态（下称**世界 A**）的遗留。toC pivot 后它与出图主链路（`listing_*`）**零外键关联**、悬空成死代码 + 一个会误导用户的「客户」导航页。

## 二、决策（用户 2026-06-12）

1. **整体移除世界 A**，不留兼容壳、不做迁移适配（遵仓库铁律：老代码适配新架构、非反向）。
2. **不留「品牌预设」**：`customer` 表的 brand_color/common_taboos/common_sizes 等字段一并删，不降级保留。
3. **删 8 张表**（已签字，见 §四）。
4. **成本看板 = 案 A**：现看板查空老表、显示全 0、看不到真实 toC 成本，已是坏空壳 → 随世界 A 整删；「真正能看 toC 成本的新看板」入 backlog，以后按 `listing_*` + `cost_ledger` 重新设计（owner PM）。
5. **角色文案 = 档 a**：注册页「默认设计师角色」等 UI 字面 → 中性「用户」（纯前端）；`app_user.role` 的 DB 枚举值**不动**（改值需迁移、收益纯字面、不值当）。

## 三、范围（整删 / 改造 / 必保）

dev AST 图谱 + frontend-b 调研双向印证：**无 STOP 级硬缠绕，可拆**。我先前担心的高危点全部排除：
- provider 共享端口 `generate()` 早已是 toC-only 签名（无 customer/family/tier/subscene/style），listing 出图 100% 走此形状——**无缠绕**。
- 老表 `generation_job/generated_image` 活链零读写，引用面仅 dashboard 链 + 死 port + 1 行 docstring。
- `cost_ledger` 结构干净（仅 user_id/amount/created_at、零世界 A 维度），是 toC 计费命脉、完整保留。

### 整删（后端）
- ORM/domain/ports/repos/services/routes/schemas 中世界 A 专属部分：customer / project / brief / asset / revision / deliverable + 老 generation_job / generated_image 全套（含 `customer_repo.py`、`customer_service.py`、`routes/customers.py`、`project_*`/`revision_*`/`dashboard_schemas`、死 port、`failover.py`）。
- 世界 A 专属枚举：dev 蓝图判定 **11 删 / 3 保**（保 `ModelName` / `TaskEventType` / `Role`；删 SubScene/Tier/Family/Style/Category/Material/ProjectStatus/JobStatus/AssetKind/RevisionStatus/GenMode）。注意 **Category 枚举 ≠ listing 的 category**（listing 用 `"FOOD"` 字符串 + CategoryCardRegistry，零引枚举），删枚举不碰 listing。
- dashboard 链：`cost_report.py`/`cost_query.py` 的世界 A 聚合 + `routes/dashboard.py`。

### 整删（前端）
- `pages/CustomersPage.tsx` + `components/project/CreateCustomerDialog.tsx`（project/ 目录删空）+ `api/customers.ts` + `/customers` 路由 + nav「客户」项。
- `DashboardPage` + `api/dashboard.ts` + CostCharts + KpiCard 四件套 + nav「业务仪表盘」+ 路由。
- `components/PagePlaceholder.tsx`（零引用死文件）。
- `schema.d.ts`/`openapi.json` 中世界 A 类型（codegen 产物，后端拆完重拉 `gen:api` 自动消失）。

### 改造（最小）
- `guard.py`：1 行 docstring 注释去世界 A 措辞。
- 注册页「设计师」文案 → 「用户」（纯前端、零后端）。
- openapi 重生 + 前端 codegen 重拉。

### 必保（与世界 A 零交叉）
- 后端：`listing_*`×3 表、`cost_ledger`、`app_user`、`model_config`、provider `generate()`、auth/listing/uploads、guard 预扣链。
- 前端：auth/listing/uploads 全家、AdminUsers/AdminModels、RoleRoute、client/errors/query-client 基建。

## 四、DB 迁移（已签字）

DROP（children-first 顺序）：

```
generated_image → generation_job → deliverable → revision → asset → brief → project → customer
```

共 **8 张**。保留 6 张：`model_config` / `cost_ledger` / `app_user` / `listing_job` / `listing_image` / `listing_job_input`。

**生产这 8 张表已全 0 行**（ops 2026-06-12 清理核验 #762）= **零数据损失**。ops 执行前强制 mysqldump 备份、可回滚。

## 五、不做（YAGNI / backlog）

- 品牌预设功能：不做。
- toC 成本看板：backlog，按 `listing_*` + `cost_ledger` 重设计（owner PM）。
- 角色枚举值改名、ModelName 枚举瘦身：不做（前者要迁移纯字面、后者与 model_config seed 互锁）。

## 六、验收

1. listing / uploads / auth / 出图 全链路**零变化**（回归绿）。
2. `/customers`、`/dashboard` 及前端对应页 → 404 / 不存在。
3. 8 表已 DROP、保留 6 表完好、`cost_ledger` + `listing_*` 数据完整。
4. 后端 tests（删世界 A 用例后）全绿。
5. prod smoke：登录 → 出图 → 计费正常；管理后台无死链。

## 七、落地编排

dev（删码 + 8 表 DROP 迁移 + openapi 再生）→ frontend-b（整删 + codegen 重拉）→ QA（回归：listing 零变化 + 两路由 404 化 + dashboard 消失）→ ops（mysqldump 备份 + DROP 迁移 + 部署 + prod smoke）→ PM（开追踪 ISSUE + 更新 PRD 去掉设计中台/客户/设计师框架 + 记 toC 成本看板 backlog）。
