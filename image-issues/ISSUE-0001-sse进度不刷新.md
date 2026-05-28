---
id: ISSUE-0001
title: SSE 任务进度被缓冲，前端进度条不实时刷新
status: 已关闭        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发
owner: —              # 已关闭，无需推进
created: 2026-05-28
updated: 2026-05-28
related:
  - PRD: §6.3.1 SSE 实时进度
  - code: image-code/api/sse.py
  - test: image-qa/cases/sse-progress.md
---

## 现象
出图任务运行中，前端 EventSource 收不到中间进度事件，直到任务结束才一次性收到全部事件，进度条全程卡在 0%。

## 复现步骤
1. 起一个 6 候选的出图任务
2. 前端打开任务详情页，观察进度条
3. 后端经 nginx 反代访问（非直连 8000 端口）

## 期望 vs 实际
- 期望：task_started / image_generated 等事件逐条实时到达，进度条增量推进
- 实际：全程无事件，任务完成瞬间一次性收到全部

## 环境 / 上下文
- nginx 反代 + FastAPI SSE endpoint
- 直连后端 8000 端口正常，过 nginx 异常 → 疑似响应流被缓冲

## 处理记录
- 2026-05-28 10:00 [开发] 创建，状态=待复现，owner→QA，疑似 nginx 缓冲了 SSE 响应流
- 2026-05-28 11:20 [QA] 已复现：过 nginx 必现、直连不现，确认为缓冲问题。状态=已确认，owner→开发
- 2026-05-28 14:00 [开发] 接手，状态=修复中
- 2026-05-28 14:40 [开发] SSE 响应加 `X-Accel-Buffering: no` 头（nginx 见此头即不缓冲该响应，无需改 nginx.conf）。状态=待验证，owner→QA
- 2026-05-28 16:00 [QA] 回归通过：过 nginx 进度实时逐条刷新。状态=已修复
- 2026-05-28 16:05 [QA] 关闭。状态=已关闭，owner→—
