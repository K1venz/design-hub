---
id: ISSUE-0008
title: 「监控」包整包缺失：/metrics 404，无 prometheus 依赖与埋点
status: 待复现        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: 开发
created: 2026-06-02
updated: 2026-06-02
related:
  - test: image-qa/2026-06-02-e2e-集成验证.md（步骤10）
  - code: image-code/src/design_hub/interface/api/asgi.py（include_router 列表无监控）
  - code: image-code/pyproject.toml（无监控依赖）
---

## 现象
任务范围声明「9 个并行包 = WP-A~H + 监控」，但**监控包在工作树中不存在**：
- `GET /metrics` → **404 Not Found**。
- pyproject 无任何 `prometheus`/`prometheus-fastapi-instrumentator`/`opentelemetry`/`statsd` 依赖。
- 全树 `grep -niE "metrics|prometheus|instrumentat"` 仅命中无关的 `time.perf_counter()` 与 export_query 的局部 `counter` 变量，无监控埋点。
- OpenAPI 共 26 个端点，无 `/metrics` 或任何可观测性路由。

## 复现步骤
1. 起 API（asgi:app）。
2. `curl http://127.0.0.1:8000/metrics` → 404。
3. `curl http://127.0.0.1:8000/openapi.json` 路径列表中无 `/metrics`。

## 期望 vs 实际
- 期望：`GET /metrics` 返回 Prometheus 文本（`# HELP`/`# TYPE`），且出图后相关 Counter/Histogram 增长。
- 实际：端点不存在（404），无任何监控埋点与依赖 → 生产可观测性缺失。

## 环境 / 上下文
- 被测 `main` @ 66c3585，9 包合并后。其余 8 包（WP-A~H）端点齐全，唯「监控」整包未落地。
- 不阻断核心业务流，故 P2；但属"声明已包含却完全缺失"的范围缺口，需 PM/开发确认是否补做或调范围。

## 处理记录
- 2026-06-02 [QA] E2E 验证步骤10 发现监控包整包缺失（端点+依赖+埋点三缺）。开单，owner→开发。状态=待复现。
