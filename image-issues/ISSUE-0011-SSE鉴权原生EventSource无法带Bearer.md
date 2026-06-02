---
id: ISSUE-0011
title: SSE 端点需 Bearer，但原生 EventSource 无法设自定义请求头
status: 待复现        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 前端
owner: 开发
created: 2026-06-02
updated: 2026-06-02
related:
  - code: image-code/src/design_hub/interface/api/routes/async_generation.py
  - code: image-web/src/api/client.ts
  - 接口: GET /generate/{job_id}/events (SSE)
  - 前端卡: docs/前端工作包拆分.md FE-3
---

## 现象
asgi 全端点（除 `/auth/*`）需 `Authorization: Bearer <JWT>`。前端 FE-3 用 **原生 EventSource**
（PRD §6.1 指定）消费 `GET /generate/{job_id}/events` 的 SSE 进度流，但浏览器原生 `EventSource`
**不支持设置自定义请求头**，无法带 Bearer，请求会被鉴权拦截（401）。

## 复现步骤
1. 登录拿 JWT。
2. 前端 `new EventSource('/api/generate/<job_id>/events')` —— 无法附加 Authorization 头。
3. 后端 include 级 `login_required` 依赖校验 Bearer → 401，SSE 建连失败。

## 期望 vs 实际
- 期望：前端能在带身份的前提下订阅 SSE 进度。
- 实际：原生 EventSource 无法带 Bearer，鉴权端点拒绝连接。

## 建议方案（择一，需后端决策）
1. **SSE 端点支持 query 传 token**：`GET /generate/{job_id}/events?access_token=<JWT>`，
   该路由从 query 读并校验（仅此 SSE 端点放宽，其余仍走 Bearer 头）。最贴合「原生 EventSource」。
2. 该 SSE 端点豁免鉴权但改用**不可猜的 job_id + 短期签名**鉴别（弱化，依赖 job_id 机密性）。
3. 前端改用 **fetch-stream**（fetch + ReadableStream 读 `text/event-stream`）以便带 Bearer 头——
   则无需后端改动，但偏离 PRD「原生 EventSource」。

> 前端倾向方案 1（后端小改、前端仍用原生 EventSource）。请开发确认方案后实施；
> 前端不改 image-code。另注意 **ISSUE-0010**（SSE 晚订阅丢事件无回放）会叠加影响 FE-3 订阅策略。

## 环境 / 上下文
- 前端 FE-0 已落地（image-web/），dev proxy `/api` → 127.0.0.1:8000。
- 本条为 FE-3「出图+SSE+选稿」的**前置阻塞项**，FE-0/1/2 不受影响。

## 处理记录
- 2026-06-02 [前端] 创建，状态=待复现；FE-0 交付时发现的后端协同缺口，owner 指给开发。
