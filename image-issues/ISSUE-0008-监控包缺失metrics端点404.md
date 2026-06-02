---
id: ISSUE-0008
title: 「监控」包整包缺失：/metrics 404，无 prometheus 依赖与埋点
status: 已关闭        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: —              # QA 复验通过关闭（Grafana/worker 自暴露/更多指标见后续 enhancement）
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

## QA 验证步骤（开发建议）
- 起 API 后 `curl -s 127.0.0.1:8000/metrics | head` 应见 `# HELP`/`# TYPE`（HTTP 指标，无需鉴权裸抓）。
- 出图一次后 `curl -s 127.0.0.1:8000/metrics | grep design_hub_generations_total` 对应 model/mode
  计数 +1；`design_hub_images_generated_total` / `..._generation_cost_cny_total` / `..._latency_seconds` 增长。
- 注：/metrics 不挂 WP-G 鉴权（instrumentator 直接加路由）；**异步 worker 进程指标暂未独立暴露**
  （见处理记录"后续项"），同步 `/generate` 的指标可在 API /metrics 看到。

## 处理记录
- 2026-06-02 [QA] E2E 验证步骤10 发现监控包整包缺失（端点+依赖+埋点三缺）。开单，owner→开发。状态=待复现。
- 2026-06-02 [开发] 监控包已落地（六边形/DIP）：
  **依赖**：`uv add prometheus-fastapi-instrumentator sentry-sdk`(带 prometheus-client)。
  **端点**：`infrastructure/monitoring/setup.py` instrument_app → 暴露 `GET /metrics`(直接加路由,
  不经 include_router 故不被 WP-G 鉴权拦,供 Prometheus 裸抓);自动采集 HTTP 指标(QPS/时延/状态码/在途)。
  **业务埋点**：`MetricsSink` 端口(DIP,默认 NoopMetricsSink 保 dev/CI 不变) + `PrometheusMetricsSink`
  实现 + `monitoring/metrics.py` 定义 Counter/Histogram(generations_total{model,mode}、
  images_generated_total{model}、generation_cost_cny_total{model}、generation_latency_seconds{model})。
  `GenerationPipeline` 成功后 record_generation;asgi+worker 注入 PrometheusMetricsSink。
  **Sentry**：init_sentry(dsn)，DSN 空则 no-op;新增 settings.sentry_dsn。structlog 原已接(config/logging.py)。
  smoke 验证:/metrics 200 + `# HELP/# TYPE`;一次 mock 出图后 generations=1、images=3、cost/latency 增长;
  Sentry 空 DSN 不崩。ruff+mypy(165) 绿。
  **本次范围 vs 后续**(建议新开 enhancement 而非阻塞本单):①Grafana 4 面板属运维侧外部配置;
  ②worker 进程 /metrics 自暴露(现 worker 已埋点到本进程 registry,但未独立 HTTP 暴露,异步出图指标暂未被抓);
  ③更多业务指标(可用率/改稿率/队列长)需触 WP-C/D 服务,留增量。
  状态→待验证, owner→QA。
- 2026-06-02 [QA] **复验通过关闭**：真实库起 API，`GET /metrics`→200 + prometheus 格式；mock 出图后
  `design_hub_generations_total{mode="text2img",model="seedream-5"}=1`、`images_generated_total=1`、
  `generation_cost_cny_total=0.2`、`generation_latency_seconds` 直方图均 present/增长。证据 image-qa/verify_fixes.py。
  后续项(Grafana 面板 / worker 进程 /metrics 自暴露 / 可用率·改稿率·队列长 指标)建议 PM 新开 enhancement，不阻塞本单。状态=已关闭。
