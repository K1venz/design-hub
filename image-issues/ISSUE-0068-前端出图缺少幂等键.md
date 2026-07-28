---
id: ISSUE-0068
title: 前端出图请求缺少 Idempotency-Key
status: 待验证
severity: P1
reporter: 开发
owner: QA
created: 2026-07-28
updated: 2026-07-28
related:
  - code: image-web/src/api/listing.ts
  - code: image-code/src/design_hub/interface/api/routes/listing.py
  - code: image-code/tests/test_listing_submission.py
---

## 现象

Stage A 后端要求所有 `/listing/generate`、`/listing/clone`、`/listing/edit`
请求携带 `Idempotency-Key`，但前端统一提交函数 `postJson` 未发送该请求头，
导致用户从工作台点击生成时收到 HTTP 400。

## 复现步骤

1. 启动已迁移到 `a7b8c9d0e1f2` 的本地 API、Redis Streams Worker 和前端。
2. 登录后进入 `/set`，上传产品图并点击生成。
3. 检查浏览器网络请求和 API 响应。

## 期望 vs 实际

- 期望：前端为每次用户提交意图生成一个稳定、不可预测的幂等键，并通过
  `Idempotency-Key` 请求头发送；后端返回 202。
- 实际：请求头缺失，后端按 fail-fast 契约返回 400
  `Idempotency-Key header is required`。

## 环境 / 上下文

- 本地后端已验证：手工携带幂等键时，三张 Mock 套图全部完成，Redis
  Consumer Group 最终 `pending=0`、`lag=0`。
- CI/单元测试此前只覆盖请求体构造，没有覆盖前端 HTTP 请求头与后端新契约的集成。
- 修复需位于 `image-web`，超出当前开发角色仅可写 `image-code + image-issues`
  的目录边界，由 PM 指派具备该目录写权限的角色。

## 处理记录

- 2026-07-28 [开发] 本地端到端验收确认，状态=已确认，owner=PM
- 2026-07-28 [开发] 前端提交函数补充 UUID `Idempotency-Key` 并新增 HTTP 边界回归测试，状态=待验证，owner=QA
