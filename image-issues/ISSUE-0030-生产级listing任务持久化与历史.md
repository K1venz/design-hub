---
id: ISSUE-0030
title: 生产级 listing 任务持久化 + 历史查看（B 专表，全独立新增、零影响现有接口）
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 用户要求的生产级核心功能；listing 出完图无留存/无历史，生产不可交付
reporter: PM          # 用户提出，PM 设计 + 排期
owner: 前端           # 历史页（ISSUE-0020 延伸）主执行；QA e2e 并行；Ops 部署跑迁移。详见处理记录
created: 2026-06-05
updated: 2026-06-05
related:
  - PRD: §3.12.9（生产级持久化与历史）
  - code: image-code/src/design_hub/ports/listing_history.py（ListingHistory 端口，现绑 NoOp）
  - code: image-code/src/design_hub/infrastructure/listing_history_noop.py（待替换为 DB 实现）
  - issue: ISSUE-0029（图片访问 /img/<sha>.png 已上生产，本条复用、不新增图片代理）
  - issue: ISSUE-0020（前端历史页延伸）
---

## 背景 / 需求
用户拍板：listing 每次出图任务**持久化**（任务 + 每张生成记录 + 输入产品图）+ **历史查看**。
**要生产级、非 MVP**（做完即可上生产）。表方案 **B**（新建 listing 专表，与海报流彻底分开）。
**硬约束：全独立新增，不影响其他接口。**

## 设计原则：additive，零改动现有
- **不碰** `generation_job`/`generated_image`/`image_store`/海报流/项目流/现有 `/projects/*` 端点。
- `ListingHistory` 端口已存在（现绑 `NoOpListingHistory`）→ 只换 listing 自己的装配为 DB 实现，海报流走的是另一条 `JobRepository`，不受影响。
- **图片访问复用 ISSUE-0029**（nginx `/img/<sha>.png`，已上生产、公开读）；本条**不新增任何图片端点**。

## 新建 3 张表（B 方案）
**`listing_job`**（一次出图任务）
```
id str PK / user_id str INDEX / prompt Text / modifiers JSON / platform str INDEX(冗余,筛选)
/ ratio str / size str / n int / status str INDEX(生成中|完成|部分完成|失败)
/ total_cost Decimal / error Text NULL / created_at datetime INDEX / completed_at datetime NULL
```
**`listing_image`**（任务下每张候选图）
```
id int PK / job_id str FK INDEX / image_key str(文件名 <sha>.png，**不存绝对 url**)
/ seed int / cost Decimal / status str(成功|失败) / created_at datetime
```
**`listing_job_input`**（输入产品图，供历史回显）
```
job_id str FK INDEX / upload_key str / ord int
```

## 持久化
- 新增 `ListingHistory` 的 DB 实现，替换 `NoOpListingHistory`（仅改 listing 装配 `composition.py`）。
- 出图结束写 `listing_job` + 每张 `listing_image` + `listing_job_input`。
- `image_key` 从出图结果 url 取文件名（`/img/<sha>.png` → `<sha>.png`），**不改 `image_store`**（ISSUE-0029 刚改过，再动会波及海报流）。
- 部分失败（选 N 张、上游挂部分）：任务 `status=部分完成`，成功的图照存照看。

## 历史端点（listing 独立，user_id 隔离）
- `GET /listing/jobs?limit=&offset=` → 当前用户任务列表（时间倒序、分页）：首图 key/平台/比例/张数/成本/状态/时间。
- `GET /listing/jobs/{id}` → 详情：任务元数据 + 全部候选图 + 输入图；**只能看自己的**（非本人 → 403/404）。
- 返回时 `image_key`/`upload_key` 拼成可访问 url：`{IMAGE_PUBLIC_BASE_URL}/img/{key}`（复用 ISSUE-0029）。
- 交互：**纯浏览 + 重新下载**（无收藏/选稿标记，用户已定）。

## 图片访问（复用 ISSUE-0029，不新增）
- 0029 已用 nginx `location /img/` 反代 `/data/docker/design-hub/generated`（prod 部署、curl 200、公开读、autoindex off 防遍历）。
- 0030 历史展示直接拼 `{IMAGE_PUBLIC_BASE_URL}/img/{image_key}`。零新增图片端点。

## OSS（阶段 2，押后）
- `LocalImageStore` → `OssImageStore`（LSP 替换）+ AK/SK 凭据。
- 因 DB 存 **key 不存 url**，切 OSS 后历史老图自动变 OSS url、**DB 零迁移、无死链**。需用户给凭据时另排（~1.5 人天）。

## 排期（生产级，~4.5 人天；复用 0029 省掉图片代理）
| # | 工作项 | 估时 | owner |
|---|---|---|---|
| 1 | 建 3 表 + Alembic 迁移 | 0.5 | 开发 |
| 2 | `ListingHistory` DB 实现替 NoOp + 出图后写任务/图/输入 | 0.8 | 开发 |
| 3 | `image_key` 从 url 取文件名落库（不改 image_store） | 0.2 | 开发 |
| 4 | 历史端点 `GET /listing/jobs`(分页) + `/{id}` 详情 + 权限隔离 | 0.8 | 开发 |
| 5 | 前端历史页：列表(分页/缩略) + 详情(候选图+输入图) + 入口 | 1.5 | 前端 |
| 6 | QA：持久化 + 历史 + 分页 + 权限隔离 e2e | 0.8 | QA |

依赖：后端 #1–#4（契约定下）→ 前端 #5 / QA #6 并行。OSS（阶段2，+1.5）押后，存 key 已铺路。

## DB 确认（涉及建表，已征求用户）
用户已拍 **B 专表** + 上述 schema 草案 + 纯浏览下载 + 零影响其他接口。开发实施时核迁移/连接（沿用现有 MySQL，不新增连接）。

## 期望 vs 实际
- 期望：每次 listing 出图留存任务+生成记录+输入图，用户可在历史页回看自己的任务、重新下载；图片复用 /img/，OSS 可平滑切。
- 实际：listing 现绑 `NoOpListingHistory` 不持久化，无历史端点、无历史页。

## 处理记录
- 2026-06-05 [PM] 用户要生产级 listing 持久化+历史，拍 **B 专表** / 纯浏览下载 / **不影响其他接口**。
  PM 设计为**全独立新增**（不碰 generation_job/image_store/海报流/项目流）；图片访问**复用 ISSUE-0029 的 /img/**（已上生产）、
  `listing_image` 存 key 便于 OSS 零迁移；撤掉原草案里会波及海报流的「image_store url→key 重构」。
  已更新 PRD §3.12.9（删押后的「历史不持久化」）。开本条派开发，owner=开发，severity P1，status=已确认。
  连带：前端历史页（ISSUE-0020 延伸）、QA e2e。OSS 为阶段2（待凭据另排）。
- 2026-06-05 [PM] **节奏：后端先行**。前端历史页 / QA e2e **暂不启动**——待开发把 3 表 + 历史端点
  （`GET /listing/jobs`、`/{id}`）契约落定（返回字段 / 分页参数 / url 形态）后，PM 据真实契约再派前端/QA，
  避免对未定契约返工（鉴 listing 前两次前端返工教训）。**前端/QA 现阶段请勿提前对接 listing 历史。**
- 2026-06-05 [开发] **后端 #1–#4 全部完成**（commits f8c99d2 / ab641a2 / 2cbb7d3），契约落定如下，PM 可据此派前端/QA：

  **① 建表 + 迁移**（f8c99d2）：3 表 `listing_job`/`listing_image`/`listing_job_input`，Alembic
  `6420ac5f02e7`（down_revision=4a2a261611d9）；手删 autogenerate 夹带的 app_user 假 diff，零改动现有表。
  临时 sqlite 验证表/列/downgrade 可逆。**⚠️ 需 Ops 部署时 `alembic upgrade head` 应用到 prod MySQL**（建表，沿用现连接）。

  **② 持久化**（ab641a2）：`SqlAlchemyListingHistory` 替 NoOp（仅 listing 装配，不碰海报流 JobRepository）；
  出图**成功与失败都落库**——成功写 `完成`（len(图)<n→`部分完成`），失败发 task_failed 后写 `失败`(0成本+error)；
  `image_key`/`upload_key` 存文件名（不存绝对 url，OSS 零迁移）。不改 image_store。

  **③ 历史端点**（2cbb7d3，**契约**）：
  - `POST /listing/generate`（**契约微调**）：入参 JSON `{upload_ids[≤3], prompt, ratio, n, modifiers{}}`，Bearer。
    **身份改用 JWT（`AuthUser.user_id`），弃 `X-User-Id` 头**——历史"只看自己的"必须按认证身份，否则按可伪造的头过滤是越权漏洞；成本/落库/历史同钉认证用户。前端**无需再传 X-User-Id**。
  - `GET /listing/jobs?limit=&offset=`（Bearer，默认 limit=20，1..100；offset≥0）→ 本人任务、时间倒序、全序分页。
    列表项：`{job_id, status, platform, ratio, n, total_cost, created_at, first_image_url, image_count}`。
  - `GET /listing/jobs/{job_id}`（Bearer）→ 详情，**仅本人**，非本人/不存在→**404**（不泄露存在性）：
    `{job_id, prompt, modifiers, platform, ratio, size, n, status, total_cost, error, created_at, completed_at,
    images:[{url, seed, cost, status}], input_urls:[...]}`。
  - **图 url**：后端已把 `image_key`/`upload_key` 拼成 `{IMAGE_PUBLIC_BASE_URL}/img/{key}`（复用 ISSUE-0029，零新增图片端点）。前端直接 `<img src=url>`。
  - `status` 取值：`完成|部分完成|失败`（`生成中` 为 schema 预留，本期"出图结束写"不产生；实时进度仍走 SSE）。

  门：ruff+mypy(191)+各阶段 sqlite in-process 冒烟（建表/downgrade、持久化成功+失败、历史隔离/分页全序/详情/url/跨用户404）全绿。
  **状态→待验证，owner→PM**：请据本契约派 ① 前端历史页（ISSUE-0020 延伸）② QA e2e（持久化+历史+分页+权限隔离）；
  并知会 **Ops 部署时跑迁移**。真实 MySQL e2e（落库+历史回看）待受控环境，与 QA/Ops 协调。
- 2026-06-05 [PM] 后端契约已落定，**据真实契约派下游三方**：
  ① **前端**（owner→前端，主执行）：历史页（列表分页 + 详情：候选图+输入图 + 入口）；按真实端点 `GET /listing/jobs`/`/{id}` 字段对接；
     **⚠️ 去掉 `X-User-Id` 头**（身份已改 JWT，前端只带 Bearer，历史/出图自动按本人）。
  ② **QA**（并行）：持久化 + 历史 + 分页 + 权限隔离 e2e；**重点验越权**（A 用户的 token 取 B 的 `job_id` → 404）；受控环境先 `alembic upgrade head` 建表再真 MySQL e2e。
  ③ **Ops**（部署时）：`alembic upgrade head`（迁移 `6420ac5f02e7`）应用到 prod MySQL（沿用现连接，纯建表）。
  PM 已据契约写三方 prompt 转交。owner→前端（历史页主执行），QA e2e 并行、Ops 部署时跟进。
- 2026-06-05 [运维] **③ prod 迁移已应用完成**：用含后端最新 commit（GitHub main `15cb36b`，含 `2cbb7d3` 等）的代码重建 api 后跑 `alembic upgrade head`。
  · 迁移 `4a2a261611d9 → 6420ac5f02e7 (listing job persistence)` 应用成功
  · 3 张新表 `listing_job`(13列)/`listing_image`/`listing_job_input` 已建；表总数 12→15，**原有 12 表未动**（纯新增，符合预期）
  · `alembic_version = 6420ac5f02e7`；api healthy、站点 `/`→200
  · 迁移前已 `mysqldump` 全量备份 → `/data/docker/design-hub/backups/design_hub_20260605_161830.sql`（兜底回滚点）
  · 注：CI(方案A) 这次因 **GitHub runner→上海服务器 SSH 跨境超时**失败，改**本地直连部署**（代码与 GitHub main 完全一致），结果无差异。CI 抖动属方案 A 已知短板，另议（self-hosted runner 走代理可根治）。
  Ops 部署侧完成 ✅。仍待前端历史页 + QA e2e（prod 表已就绪可对照）。
- 2026-06-05 [QA] **后端持久化+历史 e2e 验证完成（真 MySQL + 真 gpt-image，n=1 控成本）：16/17 通过**。
  脚本 image-qa/listing_history_e2e.py、listing_history_fail_e2e.py。
  · **持久化 ✅**：成功 job → `listing_job(status=完成, total_cost=1.19, completed_at)` + `listing_image`(1 行,
    `image_key=<sha>.png` **文件名非绝对url**, status=成功) + `listing_job_input`(upload_key=文件名, ord=0)；
    **失败 job**(bogus-GPT 真实失败) → `status=失败, total_cost=0, error=…, 0 图, 输入图已存` ✅。
    `部分完成`(len<n) 为命令派生，n=1 真实站点不可强制，代码已确认。
  · **列表 ✅** 字段齐 + 分页边界(limit 0/101→400、offset<0→400、正常→200)；**详情 ✅** 元数据+images[]+input_urls[]。
  · **权限隔离 ✅（重点全过）**：越权 B 取 A 的 job→**404**、不存在→404、无 Bearer→401、B 列表不含 A。
  · **图 url**：输出候选图 `…/img/<sha>.png` GET→**200 image/png** ✅。
  · **❌ 唯一 FAIL → ISSUE-0031(P2)**：历史详情**输入产品图回显 404**（input_urls 指 /img/(generated)，但上传落 assets/）。
  · **key 配置（已查清+已修）**：`.env` `GPT_IMAGE_API_KEY` 两个 key 逗号分隔；**旧代码**当单个 Bearer 发 → `401 Invalid token` 出图全败。
    **已被 `ee260d0` 多 key round-robin（composition.py 按逗号 split）修复**——两 key 轮用。QA 逐个单测：**key1、key2 单独都有效**（各出图成功）→ round-robin 可靠。无需改 .env。
  QA 后端 e2e 已通过（仅 ISSUE-0031 待修）。owner 维持=前端（历史页）。
