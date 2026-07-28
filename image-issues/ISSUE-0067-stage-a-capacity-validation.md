---
id: ISSUE-0067
title: Stage A 200 会话容量与恢复验收
status: 已确认
severity: P1
reporter: 开发
owner: QA
created: 2026-07-28
updated: 2026-07-28
related:
  - test: image-code/scripts/load_test_stage_a.py
  - test: image-code/tests/integration/test_stage_a_task_chain.py
  - doc: image-code/README.md
---

## 现象

Stage A 已提供有界容量脚本与恢复测试，但 200 人上线指标必须在独立预发布
拓扑取得实测证据；消息队列只提供稳定性与恢复能力，不会增加上游 Provider 容量。

## 复现步骤

1. 准备 200 个测试账号 JWT；前 40 个账号各准备 1 张本人上传图。
2. 使用 Mock Provider 执行 200 个并发读取会话和 40 单 × 5 张出图。
3. 在任务执行中分别终止 Worker、断开 Redis 客户端、制造 ACK 失败并恢复。
4. 每个并发档稳定后，再经上游额度确认执行真实 Provider 小流量测试。

## 期望 vs 实际

- 期望：以下所有验收项通过并附报告、指标截图和故障注入记录。
- 实际：测试工具和自动化断言已就绪，预发布容量数据尚未产生。

## 环境 / 上下文

验收门禁：

- 200 个已认证读取/SSE 会话，无鉴权串号。
- 40 个用户各提交 5 张 Mock 图片，共 200 个 item。
- API P95 小于 500ms（不含上传与 SSE 等待）。
- 图片终态完整，重复图片为 0，Job terminal 事件每单恰好 1 个。
- Worker 崩溃恢复后无永久非终态 item，Pending 最终归零。
- 健康状态下 Outbox oldest age 小于 10 秒。
- SSE 断线后从 `Last-Event-ID` 回放不漏终态。
- 普通 Provider 真实并发只按 `3 → 10 → 20 → 40 → 已批准上限`
  逐档提高；每档均需确认错误率、P95、上游 429 和成本后才进入下一档。
- 4K 保持全局 1，除非单独取得额度和压测结论。
- 真实调用必须传 `--provider real --allow-real-provider`，执行前核对脚本
  打印的最大预估费用。

## 处理记录

- 2026-07-28 [开发] 创建容量门禁，状态=已确认，owner=QA
