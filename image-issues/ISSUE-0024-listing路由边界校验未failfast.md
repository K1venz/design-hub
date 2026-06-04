---
id: ISSUE-0024
title: listing /generate 边界校验未 fail-fast——n/ratio/未知下拉/空prompt 返 200+job_id 而非 4xx
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: QA             # 开发已修，交回 QA 回归
created: 2026-06-04
updated: 2026-06-04
related:
  - test: image-qa/2026-06-04-listing-一键出图测试报告.md（用例 3/5/6 + 缺陷②③）
  - test: image-qa/listing_test_http.py
  - code: image-code/src/design_hub/interface/api/routes/listing.py（generate_listing）
  - code: image-code/src/design_hub/application/listing/listing_service.py（n/图数校验）
  - spec: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md（line 82 / 159-160）
---

## 现象（主，P2）
`POST /listing/generate` 对 **n 范围 / ratio 合法 / 未知下拉值 / 空 prompt** 不在 HTTP 边界校验，
而是返回 **200 + `{job_id}`**，错误延迟到异步命令里经 SSE `task_failed` 暴露。
与 spec 不符：
- spec §4.1(line 82)：「校验在边界完成（fail-fast）：images 数量、n 范围、ratio 合法、modifiers 可解析」。
- spec §7(line 159-160)：「边界校验失败（图数 / n / ratio / modifiers 解析 / 未知下拉值）→ 4xx，不降级」。

根因：`routes/listing.py` 只同步校验「图数 1..3」与「modifiers 是 JSON 对象」就 `enqueue` 返回 job_id；
`n`/`ratio`/未知下拉/空 prompt 的校验都在 `ListingGenerationService.generate()`（被 `InProcessTaskQueue`
以 `asyncio.create_task` 异步执行）→ HTTP 早已返回 200。

## 复现（QA 实测，Mock provider，零成本）
`image-qa/listing_test_http.py`（httpx ASGITransport in-process）：
- `n=8` → HTTP **200**（期望 4xx）
- `ratio="2:1"` → HTTP **200**（期望 4xx）
- `modifiers={"platform":"未知平台"}` → HTTP **200**（期望 4xx）
- `prompt="   "`（空）→ HTTP **200**（期望 4xx）
- 对照：图数>3→409、非法JSON modifiers→400 等**确**在边界拦下。

## 期望 vs 实际
- 期望：上述非法入参在 `POST /listing/generate` 同步返回 4xx（fail-fast），不入队、不发 job_id。
- 实际：返回 200+job_id，需订阅 SSE 才见 task_failed。

## 建议修复
在路由 enqueue 前同步做完整边界校验（复用现成纯函数，无副作用）：
`ratio_to_size(ratio)`、`compose_prompt(prompt, modifiers, registry)`（含未知下拉 + 空 prompt）、
`1<=n<=7`、`1<=len(images)<=3`。任一失败 → 4xx，不入队。
（service 内保留这些校验做纵深防御无妨；关键是边界先拦。）

## 附带（次/轻，建议同批处理）
- **缺陷②(P3)**：边界 4xx 错误码不符 spec——图数/非对象 modifiers 走 `DomainError→409`、0 图 FastAPI `422`；
  spec/ISSUE-0023 均要 **400**。建议输入校验错误统一 400（如 ValueError 或在边界显式返回 400），
  DomainError(409) 留给真实领域冲突。
- **缺陷③(P3)**：`sizing._RATIO_TO_SIZE` 含 `4:3→1536×1024`，超出 ISSUE-0021 确认集（1:1/3:4/9:16/16:9）。
  与 PM 对齐保留或删除。

## 处理记录
- 2026-06-04 [QA] 测 ISSUE-0023 用例 3/5/6 发现边界未 fail-fast（200+job_id）；附错误码 409/422≠400 与 4:3 超集。
  带 Mock 复现脚本开单，owner→开发。状态=待复现。
- 2026-06-04 [开发] **已修**（commit 2649274，随 ISSUE-0026 路由改造一并落地）：
  · **主（P2）**：路由 `generate_listing` 入队前**同步**跑完所有边界校验——upload_ids 数(1..3)、n(1..7)、
    `ratio_to_size(ratio)`、`compose_prompt(prompt, modifiers, registry)`（含空 prompt + 未知下拉）；
    任一非法 → 4xx，**不入队、不发 job_id**。service 内同款校验保留做纵深防御。
  · **缺陷②（P3）**：输入校验错误统一 **ValueError→400**（`prompt_composer`/`sizing`/`listing_service`
    由 `DomainError`→`ValueError`），`DomainError`(409) 留给真实领域冲突；注：listing 路由随 0026 由
    multipart 改 JSON `upload_ids`，0 图/数量越界现走路由显式 ValueError→400（非 FastAPI 422）。
  · **缺陷③（P3）**：移除 `sizing._RATIO_TO_SIZE` 的 `4:3` 超集，比例集对齐 ISSUE-0021（1:1/3:4/9:16/16:9）。
  验证 ruff+mypy(187)+冒烟（ratio_to_size/compose_prompt/service 边界均抛 ValueError）全绿。
  状态→待验证，owner→QA 回归。**请 QA**：用 `listing_test_http.py` 复跑用例 3/5/6（现应 4xx，错误码 400）。
