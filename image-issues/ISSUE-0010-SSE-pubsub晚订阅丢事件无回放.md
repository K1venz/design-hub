---
id: ISSUE-0010
title: SSE 走 Redis Pub/Sub 无事件回放，晚订阅/重连客户端会丢已发事件
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P3          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: QA             # 已修复待 QA 复验
created: 2026-06-02
updated: 2026-06-02
related:
  - test: image-qa/2026-06-02-e2e-集成验证.md（步骤5）
  - code: image-code/src/design_hub/infrastructure/events/redis_bus.py（RedisEventBus.subscribe = pubsub）
  - code: image-code/src/design_hub/interface/api/routes/async_generation.py（enqueue 后才得 job_id）
---

## 现象
事件总线用 **Redis Pub/Sub**（`publish`/`pubsub.subscribe`），无持久化/无回放。
而 `POST /generate/async` **入队后才返回 job_id**，客户端只能在拿到 job_id 后再 `GET /…/events` 订阅——
存在固有竞态窗口：若 worker 在客户端订阅前就已发布事件（mock 出图仅 ~5ms/张，极快），
这些事件（含 `task_started`）将**永久丢失**（pub/sub 不回放）。重连客户端同理丢失断连前所有事件。

> 本次 E2E happy-path **未触发**（靠 arq poll_delay 争得订阅窗口，收全了 4 条事件）；
> 但属潜在可靠性缺陷，高负载/快任务/客户端重连下可现。与已关闭的 ISSUE-0001（nginx 缓冲）不同源。

## 复现步骤（建议）
1. 让出图极快（mock 5ms）或在 enqueue 与 subscribe 间人为加延迟。
2. `POST /generate/async` 后**延迟 1s** 再开 `GET /generate/{job_id}/events`。
3. 观察：task_started/部分中间事件已丢，stream 仅余尾部或空。

## 期望 vs 实际
- 期望：晚订阅/重连仍能拿到该 job 自始至终的事件（或至少当前状态）。
- 实际：pub/sub 无回放，订阅前事件丢失。

## 建议方向
- 换 Redis Stream（XADD/XREAD from 0，天然回放 + Last-Event-ID 续传），或事件落库 + 订阅时先补发历史。

## 处理记录
- 2026-06-02 [QA] E2E 验证 SSE 时识别 pub/sub 晚订阅丢事件潜在竞态（本次 happy-path 未触发）。开单，owner→开发。状态=待复现。
- 2026-06-02 [开发] 已修：`RedisEventBus` 由 Pub/Sub 改 **Redis Stream**——`publish` 用 `XADD`
  (+`EXPIRE` 3600s 自动清理)，`subscribe` 从 `"0"` 用 `XREAD`(block) 先回放全部历史再等新事件。
  晚订阅/重连客户端从头拿到该 job 全部事件(含 task_started)，不再丢。端口签名不变，SSE 路由零改。
  `InMemoryEventBus` 同口径(按 job 缓存历史+订阅先回放，注册队列与快照历史间无 await 保原子)，保 LSP 一致。
  smoke(临时无密码 redis :6390)验证:先发 4 事件后订阅→全回放;重订阅同 job 幂等再回放;TTL=3600;
  内存版回放+实时边订边发均收全。ruff+mypy(160) 绿。
  改动: infrastructure/events/redis_bus.py、infrastructure/events/memory.py。
  注:任务环境真实 redis 需密码(.env 缺 REDIS_URL),本验证用临时实例;QA 复验可用真实库重跑 SSE 步骤。
  状态→待验证, owner→QA。
