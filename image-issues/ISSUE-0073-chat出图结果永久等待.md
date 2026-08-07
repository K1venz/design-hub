---
id: ISSUE-0073
title: Chat 生图完成后业务事件缺失导致出图结果永久等待
status: 待验证
severity: P1
reporter: 开发
owner: QA
created: 2026-08-07
updated: 2026-08-07
related:
  - code: image-code/src/design_hub/application/chat/orchestrator.py
  - code: image-code/src/design_hub/infrastructure/queue/redis_streams.py
  - code: image-code/src/design_hub/application/tasking/outbox_dispatcher.py
  - code: image-web/src/pages/ChatPage.tsx
  - issue: ISSUE-0072
---

## 现象
上游生图 API 已返回图片，但 Chat 的“出图结果”一直停留在 `0/1` 和“图片生成中”。确认请求仍由 SSE 心跳保持存活，浏览器没有收到 `image_generated`、`task_completed` 或 `task_failed`，页面因此永久转圈。

本问题与 ISSUE-0072 不同：0072 是完整 SSE 事件已抵达后，前端终态校准替换签名 URL 导致重复下载；本问题是业务事件没有抵达 Chat，现有终态与断连校准均没有触发条件。

## 复现步骤
1. 在 Chat 选择 Nano Banana 2，提交单张生图任务。
2. 在上游控制台确认生成请求已完成并返回图片。
3. 返回 Chat，观察结果卡持续显示“出图结果 0/1”和“图片生成中”。
4. 确认页面未显示连接中断，确认请求仍由心跳保持存活。

## 期望 vs 实际
- 期望：任务完成后 Chat 必须收敛到 `1/1` 或明确失败；即使 Redis 业务事件缺失，也应以持久化任务状态为真相结束本轮流。
- 实际：`ChatOrchestrator.handle_confirm` 只等待 Redis job stream 的任务终态。空读会无限循环，SSE 心跳又阻止前端进入断连恢复，造成永久等待。

## 根因证据
- 生产页面已复现 `0/1`，结果区没有图片节点，因此不是 `<img>` 下载或签名 URL 替换延迟。
- `handle_confirm` 每 15 秒读取一次 Redis job stream；空结果没有持久化状态校验，也没有其他退出条件。
- `2669659` 的前端恢复仅在收到任务终态或请求抛错时触发。仅有 SSE 心跳时两条路径都不会执行。
- ChatOrchestrator 已注入 owner-scoped `ListingHistoryQuery`，可以在 Redis 空读窗口读取同一 job 的持久化状态，无需新增跨层依赖。

## 修复边界
- 正常路径继续实时转发 Redis `image_generated` 与任务终态，不增加重复详情读取。
- Redis 空读时读取一次当前 job 的持久化状态；仍在生成则继续等待，已终态则发出缺失的任务终态并结束本轮流。
- 不伪造 `image_generated`。缺图终态由现有前端一次性详情校准恢复，避免生成第二套图片事件构造逻辑。
- owner 校验必须沿用 `ListingHistoryQuery.get_job(job_id, user_id)`，不得绕过租户隔离。

## 验收条件
1. 新增后端测试：Redis 无业务事件、持久化 job 已完成时，Chat 发出 `task_completed` 并结束等待。
2. 新增后端测试：Redis 无业务事件、持久化 job 已失败时，Chat 发出 `task_failed` 并结束等待。
3. 新增后端测试：Redis 空读但 job 仍为生成态时不得提前结束，后续真实事件仍按原顺序转发。
4. 现有正常事件链路测试保持通过，不重复发出任务终态。
5. 生产验收观察到上游完成后 Chat 在一个 Redis 空读窗口内从 `0/1` 收敛，不再永久转圈。

## 处理记录
- 2026-08-07 [开发] 生产复现并与 ISSUE-0072 拆分；确认无限等待窗口位于 Chat Redis 空读与持久化终态之间，状态=修复中。
- 2026-08-07 [开发] Chat 在 Redis 空读时增加 owner-scoped 持久化终态校验；完成、部分完成、失败均发出缺失终态，生成中继续等待真实事件。后端全套 664 passed、5 skipped，Ruff 与 mypy 通过，状态=待验证，owner=QA。
