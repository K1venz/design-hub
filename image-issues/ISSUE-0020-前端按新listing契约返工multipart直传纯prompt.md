---
id: ISSUE-0020
title: 前端出图工作台按新 listing 契约返工（multipart 直传 + 纯 prompt 直出）
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发
owner: QA             # 两步流前端已改完；待后端 /uploads(ISSUE-0026) 就绪后 QA e2e 验收
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md
  - code: image-web/docs/出图工作台-v2-商品套图重做-设计.md
  - issue: ISSUE-0019（自由 prompt；本链路升级为核心入参）
---

## 背景
用户拍板 listing 一键出图走「**multipart 直传 + 纯用户 prompt 直出（提示词唯一杠杆）**」轻量链路，
后端设计见上方 spec。这取代了前端 v2 设计稿（`出图工作台-v2-商品套图重做-设计.md`）里几处分叉契约，
前端需返工对齐。后端会另起 `POST /listing/generate` 链路（不复用 /generate/async + project）。

## 需前端调整（对照 v2 设计稿）
1. **图片传输**：`asset_ids`（资产库）→ **multipart 直传 ≤3 张**。
   **删除"从资产库选"(AssetPickerInline)**——本链路不持久化素材、不支持图库复用（用户已确认接受）。
2. **删除 category、style 下拉**（用户拍板删除；后端编排器不参与本链路）。
3. **出图端点改对接**：
   - `POST /listing/generate`（multipart/form-data，Bearer）→ 返回 `{job_id}`。
   - `GET /listing/{job_id}/events?access_token=<jwt>`（SSE，逐张到达，沿用 ISSUE-0011 query 鉴权）。
4. **请求字段**（与 spec §4 一致）：
   - `images`: file × (1..3)
   - `prompt`: str（"商品卖点&要求"文本框 = 用户自由 prompt，本链路核心入参，落实 ISSUE-0019 第1点）
   - `ratio`: str（如 "1:1"，后端映射 size；前端"尺寸/比例并存"中**尺寸不再单独传**，由 ratio 决定）
   - `n`: int 1..7（"张数"下拉）
   - `modifiers`: JSON 字符串，通用 key→value 袋子，如 `{"platform":"亚马逊","region":"美国","language":"英文"}`
     —— **增删下拉只改这里的 key，契约不变**。
5. **不再需要**：`subscene/family/tier/asset_ids/project/快速任务（隐式建项目）` 在本链路全部去除。

## 期望 vs 实际
- 期望：前端按 `/listing/*` 新契约提交 multipart + prompt + modifiers，SSE 逐张渲染候选。
- 实际：现 v2 设计稿基于 asset_ids + project + category/style + /generate/async，需返工。

## 环境 / 上下文
- 下拉**完整枚举**（平台/国家地区/语言/比例的取值）由 PM 出（见 ISSUE-0021），前端按枚举渲染。
- 后端 `/listing/*` 实现进度见 image-code；契约以 spec §4 为准，落地前可先搭骨架。

## 处理记录
- 2026-06-04 [开发] 创建并派给前端；契约见 spec §4，背景见 spec §2(0a/0b)/§8。状态=已确认，owner=前端
- 2026-06-04 [前端] 按 spec §4 新契约**重写** v2 设计稿：multipart 直传≤3 / 纯 prompt 直出 / 删 category·style·尺寸·资产库(AssetPickerInline) / 彻底无 project / 端点改 `/listing/generate`+`/listing/{job_id}/events` / 候选选稿改「结果画廊直接下载」(去评分·保留)。mockup 同步更新(v4)。待用户复核设计稿后进实现。状态=修复中，owner=前端
- 2026-06-04 [前端] **实现完成**（计划 `image-web/docs/plans/2026-06-04-listing-workbench-frontend.md`，14 任务 commit 432aa27→ccd6835）。落地：
  - `src/lib/listing.ts`（枚举+buildModifiers+buildListingFormData+parseListingEvent+estimateCost，vitest 10 测试全过）
  - `src/api/listing.ts`（useListingGenerate multipart fetch；useListingEvents **命名事件** addEventListener，对齐后端 `event:<type>`+`data:payload`，非 onmessage）
  - 组件 `components/listing/*`（ConfigSelect/ImageUploader/ListingConfigPanel/ResultGallery/WorkbenchRail）+ `layout/WorkbenchLayout`；重写 `pages/WorkbenchPage`；路由 `/` 改 WorkbenchLayout、删 projects/:id；删旧链路 16 文件。
  - **关键对齐**：SSE 命名事件、`image_generated{url,seed}` 无 index→按到达顺序填槽、`task_completed{total_cost}`。
  - **自验**：typecheck/lint/build/vitest 全过；Playwright 真实登录态渲染工作台正常（5 下拉枚举正确、爆款图复刻 toast「敬请期待」），截图 `image-web/docs/screenshots/workbench-v2-result.jpeg`。
  - **未做（交 QA）**：真实出图 e2e（multipart→job_id→SSE 逐张到达→下载）未触发（计费+ISSUE-0024 后端边界 bug 在修）。请 QA 用 n=1 控成本验全链路。
  状态=待验证，owner=QA
- 2026-06-04 [PM] ⚠️ **契约再变（ISSUE-0026）**：用户拍板 listing 改「**先上传预览 → 再出图**」，multipart 直传被取代。
  前端需第二次返工：① `ImageUploader` 从 multipart 直传 → 先调 `POST /uploads` 拿 `{id,url}` + 本地预览；
  ② 出图改带 `upload_ids`（≤3，JSON）而非 multipart files；③ 加上传中/失败态、预览缩略图、可删除重传。
  其余（下拉枚举/prompt/SSE 逐张/结果画廊）不变。契约见 PRD §3.12.8 + ISSUE-0026；后端端点就绪后即可对接。
  原 multipart e2e 验收作废 → 转两步流验收。状态=已确认，owner=前端。
- 2026-06-04 [前端] **两步流返工完成**（commit 4672535 + adf2563，按 NO 兼容直接替换 multipart）：
  - `api/listing`：新增 `useUploadImage`（`POST /uploads` multipart 单文件，字段名 **`file`**，→ `{id,url}`）；
    `useListingGenerate` 改 **JSON body** `{upload_ids,prompt,ratio,n,modifiers}`（不再 multipart）。
  - `lib/listing`：`UploadedImage{id,url}`；`ListingGenerateInput.images→uploadIds`；`buildListingFormData→buildListingBody`（vitest 9 过）。
  - `ImageUploader` 重做：选图即逐张上传，**本地 blob 即时预览**（非 file:///非代理）+ 上传中(转圈)/失败(可重传)/完成态 + 删除，≤3。
  - `WorkbenchPage`：`uploaded` 态 + 出图传 `upload_ids` + 「新建任务」resetKey 重挂清空上传器；`ListingConfigPanel` files→uploaded、canGenerate 按已上传数。
  - **自验**：typecheck/lint/build/vitest(9) 全过。可视：本轮后端(8000)宕(/api/me 502)无法登录态截图，登录页正常渲染、前端无崩溃。
  - **待 QA 注意的契约假设**（后端 /uploads 未实现，我先按最合理假设隔离在 api 层 + buildListingBody，一处可改）：
    ① `POST /uploads` 上传字段名 = `file`（沿用 brief.py 约定）；② `/listing/generate` 为 JSON body、`modifiers` 取**嵌套对象**（非 JSON 字符串）；
    ③ 预览用前端本地 blob（更稳即时；`uploaded.url` 已存留待用）。后端就绪后若字段/形态不同，仅改 `api/listing.ts` + `buildListingBody`。
  - **待 QA**：后端 `/uploads`+`/listing` upload_ids（ISSUE-0026）就绪后，e2e 验「上传→预览→出图带 id→SSE 逐张→下载」（n=1 控成本）。状态=待验证，owner=QA。
