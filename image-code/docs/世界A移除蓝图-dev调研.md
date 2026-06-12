# 世界 A（客户/接单流）移除蓝图 — dev 只读调研

> 任务：#768。方法：AST import 图谱（全仓 96 模块 + tests 引用关系）+ 逐表/逐枚举/逐域模型
> 引用扫描，非肉眼。**只读，未改任何代码/迁移。** 前端面见 frontend-b #769（已对齐）。

## 0. 总结论

**无 STOP 级硬缠绕，可拆。** listing/uploads/auth/admin 活链与世界 A 的真实交点只有
两处，且都已定性：① dashboard 成本看板=世界 A 化石（唯一产品决策点，两案见 §1.②）；
② provider 端口早已是 toC-only（coordinator 最担心的 ③ 实际零风险）。
DROP 8 张表零数据损失（ops #762 清残留后老表在 prod 全部 0 行）。

## 1. 四个高危缠绕点核查（#768 ①-④）

### ① 老表读写 → **活链零读写**
`generation_job`/`generated_image` 引用面全集：cost 子系统（dashboard 链，见②）、
4 个零被引死 port、guard.py **一行 docstring**。listing/uploads/cost_ledger 流程零染指。
`GenerationJobRow.customer` 列（String 非 FK）仅被 dashboard 聚合可见。

### ② cost 子系统 → **命脉与化石干净分层**
- **cost_ledger = toC 计费命脉，结构性零缠绕**：列仅 `user_id/amount/created_at`
  （append-only 预扣/回滚/回正），guard→BudgetPolicy→ledger 链全活、listing 在用。
  **必须保、零改动**（仅 guard.py docstring 一行提"generation_job/仪表盘"→改字）。
- **dashboard 看板 = 世界 A 化石，且已是空壳**：`ports/cost_query.py` 自述
  「以 generated_image 为事实表、按 generation_job 的 model/project/user/tier 聚合」
  ——5 维全查老表；老表现 0 行 → 看板今天就是全零，listing 真实成本它根本不看。
  **DROP 老表后这套 SQL 直接报错，不能原样保留**。两案：
  - **案 A（dev 推荐）**：整删 dashboard 链（见 §2），「toC 成本看板」列 backlog
    （按 listing_job/listing_image/cost_ledger 重设计，维度=用户/模型/图型/时间，归 PM）。
  - 案 B：本轮重写查询层指向 listing 表——**非 trivial**（维度语义 project/tier→
    图型/编辑链全变、前端图表跟改），按铁律不硬拆；用户要保看板则 B 应是独立小棒。
  - frontend-b #769⑤ 的「保留瘦身」对应案 B；前端将跟随本判定。

### ③ provider 端口 → **已是 toC-only，零风险**
`AbstractModelProvider.generate(prompt/negative_prompt/reference_images/size/n/seed/
quality)`——无 customer/family/tier/subscene/style；openai_compat/mock 同签名；
listing 调用面 100% 此形状。`failover.py` 零被引死文件随整删档走。**无需瘦身**。

### ④ 枚举/schemas/ports/装配 → 见 §2 分档；两个跨界判定：
- **Role「设计师/管理者」**（frontend #769⑥）：枚举值=app_user.role 的 DB 字符串。
  **lean=档 a：仅改前端 UI 文案，后端枚举与 DB 值不动**（零迁移零签字）；
  档 b 改值=UPDATE app_user 数据迁移=签字项，纯字面收益，列可选后续。
- **ModelName 瘦身（SEEDREAM/WANXIANG/LINGDONG）：本轮不动**——
  `unit_cost_map()` 把 model_config 表 name 反序列化为 ModelName，删枚举值会在
  现存 4 行 seed 数据上炸；要瘦须同步 DELETE 3 行（动数据=签字）。收益低，可选后续。

## 2. 三档清单

### 【整删】（引用闭包已验：删除后无悬挂 import）
**纯死代码（零被引，14 模块 + 连带闭包）**：
- ports：`image_repository` `job_repository` `revision_repository` `asset_store`
  `project_catalog` `metrics` `vision`（+`ports/__init__` 的 VisionAssist re-export）
  `exporter`（+寄生在 storage/tos.py 里的 `TosExportStore` 类段——死类活文件，删类段）
- infrastructure：`providers/failover.py` `storage/local_asset.py` `vision/`（整目录）
  `monitoring/prometheus_sink.py` `monitoring/metrics.py` `ledger/memory.py`
  `listing/noop_history.py`
- interface：`project_catalog_schemas.py` `revision_schemas.py` `selection_schemas.py`
- `config/logging.py` `domain/project_status.py`

**customers 活链（用户拍板功能下线）**：
`routes/customers.py` + `api/project_deps.py` + `application/project/`（customer_service）
+ `infrastructure/db/customer_repo.py` + `ports/repositories.py`（Customer/Project/Brief/
Asset 四仓储抽象整档）+ `interface/project_schemas.py` + asgi 两处装配。

**dashboard 链（案 A）**：
`routes/dashboard.py` + `api/dashboard_deps.py` + `application/dashboard/` +
`ports/cost_query.py` + `infrastructure/db/cost_query.py` + `interface/dashboard_schemas.py`
+ asgi 两处装配（删后 manager_only 仅挂 admin/users）。

**domain 清理**：
- enums 整删 11 个：SubScene/Tier/TemplateFamily/Style/**Category**/MaterialType/
  ProjectStatus/JobStatus/AssetKind/RevisionStatus/GenMode（Category 枚举≠listing 的
  category——listing 用 "FOOD" 字符串+CategoryCardRegistry，已验零引枚举）；
  保 ModelName/TaskEventType/Role；`domain/__init__.py` re-export 同步。
- models.py 死域模型：CustomerRecord/ProjectRecord/BriefRecord/AssetRecord/JobRecord/
  GenerationResult 等世界 A 段（保 GeneratedImage/TaskEvent/Listing*/BudgetSnapshot）。
- models.py ORM 8 类（Customer/Project/Brief/Asset/GenerationJobRow/GeneratedImageRow/
  Revision/Deliverable）+ DROP 迁移（§3）。

**收尾**：openapi.json 再生（/customers /dashboard 消失，frontend-b 重拉 codegen 即
自动消化 #769⑦）。tests 零受影响（49 例不引世界 A，import 图谱含测试边）。

### 【需改造】（各 1 行级）
- guard.py docstring「与 generation_job/仪表盘一致」→ listing 口径。
- errors.py NotFoundError docstring「project/brief/asset」→ 改字。
- asgi.py 删两段装配（customers/dashboard）。
- Role：前端文案档 a（frontend-b 执行，后端零改动）。

### 【必须保】（被活链复用）
cost_ledger 表+ports/ledger+sqlalchemy_ledger+guard/budget（计费命脉）；model_config
表+admin 链（价格基建）；app_user+auth 链；listing 三表+全链；uploads 链；
monitoring/setup（Sentry+/metrics）；throttle；domain/media；storage local/local_upload/
tos（除 TosExportStore 段）；providers mock/openai_compat；registry；composition。

## 3. DROP TABLE 迁移清单（一支新迁移，**须用户亲签**）

按 FK 依赖序（children-first）：
`generated_image` → `generation_job` → `deliverable` → `revision` → `asset` → `brief`
→ `project` → `customer`（共 8 张）。
保 6 张：model_config / cost_ledger / app_user / listing_job / listing_image /
listing_job_input。
数据现状：8 张在 prod 全 0 行（ops #762 清残留核验）→ **DROP 零数据损失**；
downgrade 不提供（项目规则：无向后兼容）。

## 4. 实现棒预估与顺序

dev 删码+迁移+openapi 再生+门禁 ~0.5-1d；QA 回归面=listing 全链零变化（49 测试 +
边界回归）+ /customers /dashboard 404 化；frontend-b 跟随（#769：整删 0.5h +
dashboard 收敛跟本判定 + codegen 10min）。
顺序：用户签 DROP + 拍 dashboard 案 A/B → dev 删码+迁移 → frontend 跟 → QA 回归 → 部署。
