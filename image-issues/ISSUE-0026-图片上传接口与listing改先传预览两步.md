---
id: ISSUE-0026
title: 后端图片上传接口 POST /uploads + listing 改「先上传预览 → 再出图」（取代 multipart 直传）
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 用户主动需求；listing 核心交互改两步，跨后端/前端/QA 返工需协调
reporter: PM          # 用户提出，PM 排期
owner: QA             # 后端已实现，交 QA 按两步流改版用例验证
created: 2026-06-04
updated: 2026-06-04
related:
  - PRD: §3.12.1 / §3.12.8（已更新：listing 改两步 + 上传接口 + 本地存储路径）
  - code: image-code/src/design_hub/interface/api/routes/listing.py（现 multipart 直传，待改 upload_ids）
  - code: image-code/src/design_hub/infrastructure/storage/local_asset.py（LocalAssetStore，base_dir 指向 assets/）
  - code: image-code/src/design_hub/application/project/asset_service.py（已有 upload 用例可复用）
  - issue: ISSUE-0021（listing PRD）、ISSUE-0023（QA 用例14 需改版）、ISSUE-0020（前端两步流）
---

## 背景 / 需求
用户拍板：listing 一键出图从「multipart 直传」改为**两步**——**先独立上传、预览，再出图引用**。
这**取代** spec 决策 0a（`docs/superpowers/specs/2026-06-04-listing-image-generation-design.md`）的「multipart 直传 ≤3 图」。
按本仓铁律（NO 兼容层）：新形态取代直传，不并存。

## 需开发产出（后端）
1. **`POST /uploads`**（鉴权 Bearer）：`UploadFile` → 存储 → 返回 `{id, url}`。
   - fail-fast 校验：大小 ≤ 10MB、格式白名单（png/jpg/webp），违例 → 4xx（不静默）。
   - `id` = 存储键（可复用 LocalAssetStore 的 sha256 hash 名）；`url` = 后端代理 url（见 2）。
2. **`GET /uploads/{id}`**：后端读图代理，从存储读回 bytes 按正确 content-type 返回，供前端预览。
   - **不暴露 `file://`**（现 LocalAssetStore.save 返回 file:// 不能直接给前端，预览统一走本代理）。
3. **listing 改造**：`POST /listing/generate` 入参从 `images: list[UploadFile]`（直传）→ **`upload_ids: list[str]`（≤3）**。
   服务端按 id 从存储 `load()` 读回 bytes → 发上游 `/images/edits`。其余链路（prompt 组装 / CostGuard / SSE / N 次单图）不变。
   - 边界：upload_ids 数量 0 或 >3 → 400；id 不存在 → 4xx。

## 存储方案（用户已定：服务器本地磁盘，不用 OSS）
挂进 docker api 容器的持久化卷：

| 用途 | 路径 |
|---|---|
| 上传产品图/参考图 | `/data/docker/design-hub/assets/` |
| AI 出图落点 | `/data/docker/design-hub/generated/` |
| 导出归档 | `/data/docker/design-hub/exports/` |

- 沿用 `LocalAssetStore`，`base_dir` 经 `.env` 指向 `assets/`（部署环境已挂卷，持久化）。
- **不引入 OSS / 不需凭据**；预览经 `GET /uploads/{id}` 代理。
- OSS 公网/CDN（`OssAssetStore` LSP 替换 + AK/SK）作**后续增强**，本期不做。

## ⚠️ 返工范围（PM 已向用户挑明并确认推进）
- 后端：listing `/listing/generate` 已实现的 multipart 直传 → 改 upload_ids（本条）。
- QA：**用例14 已花 ¥1.19 实测通过的 multipart e2e** 需改版为两步流重测（ISSUE-0023）。
- 前端：已做的直传组件 → 改「上传 → 预览 → 出图带 id」（ISSUE-0020）。

## 排期（人天，本地存储方案）
| # | 工作项 | 估时 | owner |
|---|---|---|---|
| 1 | `POST /uploads` + `GET /uploads/{id}` 代理 + 校验 | 0.8 | 开发 |
| 2 | listing：multipart → `upload_ids`，后端按 id 读回 bytes | 0.5 | 开发 |
| 3 | 前端：上传组件 + 预览 + 出图带 id（ISSUE-0020 修订） | 1.0 | 前端 |
| 4 | QA：用例14 改版（两步流）+ 上传 e2e | 0.5 | QA |
| **合计** | | **~2.8** | |

依赖：后端 #1#2（契约定下）→ 前端 #3 / QA #4 并行。OSS 化（+1.5）押后，要上再给凭据。

## 期望 vs 实际
- 期望：用户上传产品图 → 预览 → 出图引用 upload_ids，图存服务器本地 `assets/`，预览经后端代理。
- 实际：现 listing 为 multipart 直传一步、存储返 file:// 前端不可预览、无独立上传端点。

## 处理记录
- 2026-06-04 [PM] 用户提出「后端缺真实上传接口」并拍板：独立 `POST /uploads` + 先上传预览 → 再出图；
  存储用服务器本地 `/data/docker/design-hub/assets/`（挂 docker 卷），不用 OSS。
  PM 已挑明此举取代 listing multipart 直传（spec 0a）、涉及后端/前端/QA 返工，用户确认推进。
  已更新 PRD §3.12.1/§3.12.8。开本条派开发（后端端点 + 代理 + listing 引用改造），owner=开发，severity P1，status=已确认。
  连带：前端两步流改造（ISSUE-0020）、QA 用例14 改版（ISSUE-0023）。
- 2026-06-04 [开发] **已实现**（commit 2649274）：新增 `UploadStore` 端口 + `LocalUploadStore`
  （id=sha256[:16].<ext>，正则约束防路径穿越）+ `UploadService`（≤10MB / png·jpg·webp fail-fast）；
  `POST /uploads`(Bearer)→`{id,url}`、`GET /uploads/{id}`(`?access_token=` 读图代理，按 content-type
  返 bytes，不暴露 file://)；listing `/generate` 入参 multipart files → JSON **`upload_ids`(≤3)**，
  服务端按 id `load()` 字节发上游，ListingService/Command 不变。
  **架构说明（给 PM）**：用**专用 UploadStore** 而非字面复用 `LocalAssetStore`——后者契约 `save→file://url
  / load(url)` 给不出干净的 `id`+content-type，强复用需在新代码塞 id↔url 转换（shim，违铁律）。专用端口
  满足你全部实际约束（本地磁盘 / 无 OSS / 无 DB）、**写同一 `assets/` 目录**、零 shim。OSS 化仍可 LSP 替换。
  验证 ruff+mypy(187)+冒烟（上传 roundtrip / 大小格式 fail-fast / 路径穿越 / 缺失 404 / 路由挂载）全绿。
  spec §2/§3/§4 已更新为两步流。状态→待验证，owner→QA。**请 QA**：按 ISSUE-0023 改版用例（两步流：
  上传端点 + upload_ids 出图）重测；多图 image[] 与真实 e2e 仍需受控环境（plan §5.3 / ISSUE-0025）。
