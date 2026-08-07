---
id: ISSUE-0072
title: Chat 终态校准替换 SSE 签名 URL 导致结果图重复加载
status: 待复现
severity: P2
reporter: 开发
owner: QA
created: 2026-08-07
updated: 2026-08-07
related:
  - code: image-web/src/pages/ChatPage.tsx
  - code: image-web/src/components/listing/use-terminal-job-reconciliation.ts
  - code: image-web/src/lib/chat.ts
  - code: image-code/src/design_hub/interface/task_event_presentation.py
  - design: docs/superpowers/specs/2026-08-06-unified-sse-image-feedback-design.md
---

## 现象
Chat 已收到 `image_generated` 并开始加载结果图后，紧随其后的任务终态仍会无条件读取一次任务详情，并用新签名 URL 整体替换结果槽。对象相同但 URL 不同，浏览器可能取消或重复下载原图，表现为生图完成后在 Chat 中回显仍慢，4K 大图更明显。

## 复现步骤
1. 在 Chat 选择可生成 4K 的图片模型，生成一张较大的结果图。
2. 在浏览器 Network 中同时记录 Chat `/chat/confirm` SSE、`GET /listing/jobs/{job_id}` 与结果图片请求。
3. 观察 `image_generated` 已携带非空 `image_key/url` 并触发首个图片请求。
4. 观察 `task_completed` 后 `ChatPage.on` 无条件调用 `reconciliation.reconcile(jobId)`；详情返回的新签名 URL 替换 SSE URL，并检查是否触发第二个图片请求或中断首个请求。

## 期望 vs 实际
- 期望：完整 SSE 链路中，`image_generated` 的 URL 是实时展示主路径；所有槽位已收到成功或失败事件时，`task_completed` 只更新任务状态，不再读取详情、不替换 URL。仅在 SSE 缺事件或连接中断时执行一次有上限的详情校准。
- 实际：`image-web/src/pages/ChatPage.tsx` 在每个 `task_completed/task_failed` 上无条件调用终态校准，随后用 `detailToResultSlots(detail)` 整体覆盖当前槽位。

## 环境 / 上下文
- 当前主分支已包含 `1c85dc9 merge: unify SSE image feedback`。
- 后端 `present_task_event_data` 已在 `image_generated` 出口补齐签名 URL，任务事件顺序测试也锁定图片事件先于任务终态。
- Outbox 调度间隔为 0.2 秒，Redis 阻塞读取会在事件到达时立即唤醒；当前静态证据不支持把尾延迟归因于 Outbox 或 Chat SSE 缓冲。
- 修复边界：前端应基于 `settledSlotCount(state.slots) === state.jobTotal` 判断完整终态。完整时保留 SSE 槽位；槽位不完整或连接中断时才调用现有一次性 reconciler。不得通过延时、轮询或缓存签名 URL 绕过。

## 验收条件
1. 新增前端测试：完整的 `image_generated -> task_completed` 序列不调用 `fetchListingJob`，并保留 SSE URL。
2. 新增前端测试：任务终态但槽位缺失时只调用一次 `fetchListingJob`。
3. 新增前端测试：SSE 连接中断且已有 `job_id` 时仍只调用一次详情恢复。
4. 浏览器 Network 实测 1K 与 4K 各一张，正常链路每张结果图只有一次对象请求，且 SSE URL 不在终态被替换。

## 处理记录
- 2026-08-07 [开发] 复核统一 SSE 修复后的完整数据流，确认正常终态仍存在无条件详情校准与签名 URL 替换；创建问题并交 QA 做浏览器 Network 复现，状态=待复现。
