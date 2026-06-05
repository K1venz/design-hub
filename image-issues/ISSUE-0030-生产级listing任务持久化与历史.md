---
id: ISSUE-0030
title: 生产级 listing 任务持久化 + 历史查看（B 专表，全独立新增、零影响现有接口）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 用户要求的生产级核心功能；listing 出完图无留存/无历史，生产不可交付
reporter: PM          # 用户提出，PM 设计 + 排期
owner: 开发           # 后端主体：建表 + 持久化 + 历史端点
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
