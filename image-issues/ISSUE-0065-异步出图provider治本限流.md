---
id: ISSUE-0065
title: 转异步出图（apinebula image-tasks 队列）治本同步端点限流——prod 真实用户成功率 ~33%
status: 修复中        # coordinator 异步接口已实证(30s completed零失败)；dev 接 P1:先¥0.8前置实证→建 AsyncImageTasksProvider
severity: P1          # 真实用户当前受影响：prod 出图成功率 ~33%（同步端点过载即拒、串行 mitigation 不够）；非资损但核心功能可用性硬伤
reporter: coordinator  # 品类批终态全 1/3 暴露、coordinator 异步接口实证（#1101）
owner: 开发            # dev 接：先前置实证(size/input_fidelity/n 是否支持)→过则建异步 provider；ISSUE 由 PM 开
created: 2026-07-08
updated: 2026-07-08
related:
  - issue: ISSUE-0063（新 key 分组限流紧=本条根因，串行/image2-vip 是 stopgap，本条=治本）、ISSUE-0056（key 恢复=同步链）、ISSUE-0057（配置页注册表=异步 provider 挂载点，两 provider 并存/切换）、ISSUE-0055（墙钟/人话失败兜底沿用）
  - code: image-code infrastructure/providers/openai_compat（同步 provider 保留=备用渠道）、application/registry（ProviderRegistry 注册异步 provider_type）、MediaUrlSigner（现签 reference URL）、ImageStore（download_url→bytes→落存，后段复用）
  - 群聊: image-gen#1 #1101（品类批 1/3 暴露 + 异步接口实证）
---

## 现状 & 治本（coordinator #1101）
- **现状**：新 key 分组（gpt-image-2-1k）同步端点 `/images/edits` **限流紧**——并发失败、串行也挨限流（品类批终态**全 1/3**）；**prod 真实用户出图成功率 ~33%**=核心功能可用性硬伤。
- **实证治本**：同一把 KeyA，**异步任务接口** `POST /v1/image-tasks/edits`（JSON、images 传 **URL**）→ queued → **30 秒 completed 拿 download_url、零失败**。结论=同步端点过载即拒、**异步排队消化**；还带**失败自动退款**。→ **转异步是治本**（非 image2-vip 升级/串行 stopgap）。

## ⚠️ 前置实证（dev 先做、别盲建，≈¥0.8）
异步 edits 是否**尊重**以下参数（文档未列全，不支持则方案要重估）：
1. **`size`（如 `1536x1024`）**——⚠️ 若不支持=**非 1:1 比例全废**，整个方案重估（**这条最关键**）。
2. **`input_fidelity`**（产品/文字保真核心价值，734f24b 同款）。
3. **`n`**（我们全链恒 1，确认异步同语义）。
> 实证不过（尤其 size）→ 停下重估、报 PM/coordinator，别硬建。

## 实现（实证过后，dev）
- 新 `provider_type = apinebula_async_image` → **0057 注册表映射**（配置页切换即用、**与同步 provider 两存**、同步保留=备用渠道）。
- **submit**（JSON、images=**现签 URL**——⚠️ 端口今传 bytes，需把 reference 的**签名 URL** 带进 provider 调用，`MediaUrlSigner` 现成、**端口演进 dev 设计**）→ **轮询**（queued/in_progress→completed/failed，沿 `retry_max_elapsed` 墙钟语义）→ **download_url 拉 bytes → ImageStore 落存**（后段全复用、0055 失败人话/墙钟沿用）。
- 失败自动退款语义对齐现有 fail-closed 计费。

## 验收标准（QA）
1. **前置实证**：size/input_fidelity/n 支持结论明确入档（尤其 size 尊重非 1:1）。
2. **异步出图成功率**：真实/mock 队列场景成功率显著回升（对比同步 ~33%）、30s 级完成、无僵尸。
3. **两 provider 并存**：0057 配置页切默认在同步/异步间切换即生效（异步治本、同步备用）。
4. **保真不回退**：input_fidelity 生效（产品/文字保真）、size/比例正确。
5. **零回归**：ImageStore 落存/历史/计费/0055 失败兜底不变；失败自动退款正确。

## 范围外（YAGNI）
webhook 回调（先轮询）/ 异步批量并发编排 / 多中转站负载均衡。

## 处理记录
- 2026-07-08 [coordinator+PM] 品类批终态全 1/3 暴露 prod 真实用户 ~33% 成功率（同步端点限流、串行不够）→ coordinator 实证异步接口 image-tasks（30s completed 零失败+自动退款）=治本 → PM 开条挂账 **P1**（真实用户核心功能可用性）。
  **dev 接**：① 先 ≈¥0.8 前置实证（size/input_fidelity/n 是否支持、尤其 **size 非 1:1 是死穴**）；② 过则建 `apinebula_async_image` provider（0057 注册表挂载、submit 现签 URL/端口演进、轮询、download_url→ImageStore、同步保留备用）。**品类真图批（ISSUE-0060 ①⑤）等异步 provider 上线后重跑**（现 4 张 1/3 残图不作数、评图要全套）。
  **部署拆两波**：Hero 波（2d8f26f+734f24b 就绪）coordinator 先上；异步 provider 波 dev 完工后走。**知识库「明确不支持」暂不动**（异步=内部实现、非用户可见功能变更，coordinator #1101）。owner=开发（前置实证→实现）。
