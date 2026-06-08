---
id: ISSUE-0034
title: 海报/项目流把会过期的 TOS 签名 url 存进 generated_image.url，历史回看 404
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 海报/项目流回看显示；该流前端已弱化(ISSUE-0020 删项目详情)，影响有限但属真 bug
reporter: 运维        # ISSUE-0033 上 TOS 时点出
owner: QA             # 开发已修，交 QA 验回看不再过期
created: 2026-06-05
related:
  - issue: ISSUE-0033（TOS 上 prod）/ b308556（TOS 接入）
  - code: image-code/src/design_hub/infrastructure/db/job_repository.py（save_completed 存 url）
  - code: image-code/src/design_hub/interface/selection_schemas.py / project_catalog_schemas.py（读出当显示 url）
  - code: image-code/src/design_hub/application/export/export_service.py（按 source_url 读源图字节）
---

## 现象 / 根因
切 TOS 后 `ImageStore.save` 返回的是 **TOS 预签名 url（含 ?X-Tos-… query、默认 1h 过期）**。
海报流 `SqlAlchemyJobRepository.save_completed` 把它**原样存进 `generated_image.url`**。
该值被 3 处消费，过期/带 query 后都坏：
1. **选稿** `GET /jobs/{id}/images`（`ImageOut.url`）→ 显示 url 过期 404。
2. **项目候选图列举** `project_catalog`（`ProjectImageOut.url`）→ 同上。
3. **导出** `export_service` 按 `source_url` 读源图字节 → `LocalExportStore` 取 basename(`<sha>.png?X-Tos…`)
   读本地 `generated/`，既因 query 名不对、又因图在 TOS 不在本地 → 读不到。

> 与 listing 不同：listing(ISSUE-0030) 存 `image_key`、读时经 `MediaUrlSigner` 重签，故无此问题。海报流当年存的是 url。

## 修复（与 listing 一致：存 key、读时签）
1. 新增 `image_key_from_url(url)` 工具（去 ?query 再取文件名）；listing 命令的 `_image_key` 复用之（DRY）。
2. `save_completed`：`generated_image.url` 改存 **image_key**（非签名 url）。
3. **显示路径注入签名器**：`selection`/`project_catalog` 路由取 `app.state.media_signer`，
   `ImageOut.of`/`ProjectImageOut.of` 经 `signer.generated_url(key)` 出 url。SSE 仍用 save 返回的即时签名 url，无需改。

## 边界 / 跟进（本次不做）
- **导出读 TOS 源图**：存 key 后 `LocalExportStore.read(key)` 对**本地部署**已能按文件名读回；
  但 **TOS 部署**下源图在 TOS 桶、不在本地 `generated/` → 导出仍读不到，需 `TosExportStore`(从 generate 桶 get_object)
  或 export 走签名 url 下载。导出属已弱化的项目流(ISSUE-0020 删项目详情)，**标为跟进**，本次不阻塞。

## 期望 vs 实际
- 期望：海报/项目流历史回看图能长期显示（DB 存 key、读时签新 url）。
- 实际：DB 存了 1h 过期签名 url，回看 404。

## 处理记录
- 2026-06-05 [运维] 上 TOS(ISSUE-0033)时点出：海报流共用 ImageStore，generated_image.url 存的是会过期签名 url。
- 2026-06-05 [开发] 立条 + 修复中：存 key/读时签（selection+catalog），导出 TOS 读标跟进。owner=开发。
- 2026-06-05 [开发] **已修**（commit 8b5360f）：新增 `domain.media.image_key_from_url`（去 ?query 取文件名）；
  `save_completed` 把 `generated_image.url` 改存 image_key；`selection`/`project_catalog` 经新增
  `MediaSignerDep` 注入签名器、读时 `signer.generated_url(key)` 出 url。SSE 仍用 save 返回的即时签名 url。
  listing 命令 `_image_key` 复用同一工具(DRY)。验证 ruff+mypy(194)+冒烟（三形态去 query、selection/catalog
  存 key→读签出 url、app 构建）全绿。**导出 TOS 读源图**仍为跟进项（项目流已弱化，单独排）。
  状态→待验证，owner→QA。**请 QA**（若海报/项目流仍联调）：回看选稿/候选图，url 应为重新签名（本地=/img）、
  不再 1h 过期 404；新出图存的是 key（DB 查 generated_image.url 应为 `<sha>.png` 而非带 ?X-Tos 的长 url）。
- 2026-06-08 [开发] **导出读 TOS 源图收尾**（commit 210aba7 + 605393c lint）：原标"跟进"的导出项已补——
  新增 `TosExportStore`：导出 `read` 从 generate 桶按 image_key `get_object`（去 ?query 取文件名）；
  `composition.build_export_store` 按是否配 TOS 切 Tos/Local；asgi 装配改用之。**导出在 TOS 下恢复源图读取**
  （切 TOS 曾让其读本地 404，现回到可用态）。导出产物 web 下载（file://）是更早的独立限制、本次未变。
  ruff(exit0)+mypy(194)+冒烟（Tos/Local 切换、app 构建）全绿。至此 0034 后端全部完成，待 QA 验。
