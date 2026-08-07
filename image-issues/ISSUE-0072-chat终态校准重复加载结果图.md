---
id: ISSUE-0072
title: Chat 出图回显终态校准不完整，可能重复加载或永久转圈
status: 已复现
severity: P1
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

生产环境还存在更严重的第二种故障模式：上游生图 API 已返回图片，但 Chat 的“出图结果”一直停留在 `0/1` 和“图片生成中”。连接没有进入异常分支，SSE 心跳持续保持请求存活，但浏览器始终收不到 `image_generated` 与 `task_completed/task_failed`，因此现有一次性校准永远不会触发。

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
- 2026-08-07 生产复现显示最新任务为“出图结果 0/1”，没有任何结果图节点；这排除了单纯 `<img>` 下载慢或签名 URL 被替换，说明业务事件没有抵达 Chat。
- `2669659 fix: stop chat image spinners at task terminal` 只在收到任务终态或确认请求抛错时校准。SSE 仅有心跳、业务事件永久缺失时，这两个条件都不成立，页面会无限转圈。
- 需要分别核对 worker 的对象存储/数据库终态提交、Outbox 发布、Redis job stream 与 Chat 消费游标。不能把“上游 API 已返回”当成端到端完成。

## 验收条件
1. 新增前端测试：完整的 `image_generated -> task_completed` 序列不调用 `fetchListingJob`，并保留 SSE URL。
2. 新增前端测试：任务终态但槽位缺失时只调用一次 `fetchListingJob`。
3. 新增前端测试：SSE 连接中断且已有 `job_id` 时仍只调用一次详情恢复。
4. 浏览器 Network 实测 1K 与 4K 各一张，正常链路每张结果图只有一次对象请求，且 SSE URL 不在终态被替换。
5. 新增集成测试：上游已完成且持久化任务已终态、但 Chat 未收到 Redis 业务事件时，Chat 能从持久化真相收敛到终态，不会因心跳持续而永久等待。
6. 新增集成测试：只有 SSE 心跳且任务仍处于生成态时不伪造完成；一旦持久化状态终态，最多一次校准并关闭本轮流。
7. 生产验收必须同时观察 `generation_item_completed`、`generation_outbox_published`、Chat `image_generated/task_completed` 和前端 `1/1`，四段链路缺一不可。

## 处理记录
- 2026-08-07 [开发] 复核统一 SSE 修复后的完整数据流，确认正常终态仍存在无条件详情校准与签名 URL 替换；创建问题并交 QA 做浏览器 Network 复现，状态=待复现。
- 2026-08-07 [开发] 在生产 Chat 复现 `0/1` 永久转圈：SSE 请求仍存活但未收到任何业务事件。确认旧修复未覆盖“心跳存活、事件缺失”窗口，问题升级为 P1，状态=已复现。
