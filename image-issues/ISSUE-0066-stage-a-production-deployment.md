---
id: ISSUE-0066
title: Stage A 生产拓扑部署与可观测性验收
status: 修复中
severity: P1
reporter: 开发
owner: 运维
created: 2026-07-28
updated: 2026-07-28
related:
  - code: image-code/src/design_hub/interface/worker.py
  - code: image-code/src/design_hub/interface/api/asgi.py
  - doc: image-code/README.md
---

## 现象

Stage A 可靠队列代码已完成，但当前 2C/3.8GB 单机需要严格限制 Redis 与 Provider 并发；
未完成 Redis 持久化、API/Worker 进程分离和监控验收前不得放量。

## 复现步骤

1. 在预发布环境执行 `uv run alembic upgrade a7b8c9d0e1f2`。
2. 分别启动 API 与 Worker，提交 Mock 套图任务并重启 Worker。
3. 检查任务恢复、JSON 日志、Prometheus 指标、Sentry 和备份恢复。

## 期望 vs 实际

- 期望：按下列门禁完成独立部署并保留可验证证据。
- 实际：开发侧代码已就绪，生产基础设施与运维证据尚未完成。

## 环境 / 上下文

生产门禁：

- Redis 按当前上线规模使用同机独立 Docker 容器，不发布宿主机端口，启用 AOF everysec、
  256MB maxmemory、384MB 容器上限及 noeviction；规模增长后再迁移托管 Redis。
- API 与 Worker 独立进程；API 不持有 Provider 执行职责。
- 迁移前完成 MySQL 备份和恢复演练，记录迁移前 revision。
- API 与 Worker 输出 JSON 日志，集中采集且可按
  `request_id/trace_id/job_id/item_id/operation_id` 检索。
- Prometheus 抓取 Outbox age/count、Stream depth/Pending、任务终态、
  Provider in-flight/失败、SSE 连接数。
- Sentry 验证请求与任务标签；日志和事件不得包含 Prompt、图片字节、
  Authorization、API Key、Redis 凭据或签名 URL 查询参数。
- 生产密钥只通过密钥管理或受限环境变量注入。
- 默认 Provider 槽保持普通 3、4K 1；未经 ISSUE-0067 分阶段压测不得提高。
- 完成停提交流程、Worker 排空、数据库恢复和 Redis Pending 保留的回滚演练。

## 处理记录

- 2026-07-28 [开发] 创建部署门禁，状态=已确认，owner=运维
- 2026-07-28 [运维] Compose 增加独立 Worker、托管 Redis 预检和双进程健康门禁，状态=修复中，owner=运维
- 2026-07-28 [运维] 按用户确认改为同机 Docker Redis，补齐 AOF、资源上限、noeviction、强随机密钥与启动健康门禁，状态=修复中，owner=运维
- 2026-07-28 [运维] 生产验收发现 nginx 缓存重建前 API 地址并在默认日志记录 query；补齐部署后平滑 reload 和无查询串访问日志，状态=修复中，owner=运维
