---
id: ISSUE-0007
title: gpt-image /images/edits（图生图）真实调用 180s 超时，回落 mock；文生图正常
status: 待复现        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: 开发            # 球在开发
created: 2026-06-02
updated: 2026-06-02
related:
  - test: image-qa/2026-06-02-e2e-集成验证.md（步骤4）
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py（_edit/_request_multipart）
  - code: image-code/src/design_hub/application/pipeline.py（_generate_with_fallback）
---

## 现象
带产品素材的项目出图（图生图，应走 `/images/edits` multipart），真实 gpt-image-2-vip 调用
**恰好 180s 超时**（= provider `timeout=180.0` 上限），抛 `ProviderTimeout` 被 fallback 捕获，
回落到同档备选 seedream-5（mock），最终 `used_model=seedream-5`、`url=mock://…`。
→ **图生图保真主链路当前拿不到真实图**（仅静默降级为 mock）。

对照：**不带素材的文生图**（`/images/generations`）真实调用 **64.5s 成功**，
`used_model=gpt-image-2`、真实 `file://` 落盘 1024×1024 PNG。说明中转站连通/鉴权/模型均正常
（`GET /models` 200/4.0s，`gpt-image-2-vip` 在列），**问题定位在 edit（图生图）请求本身**。

## 复现步骤
1. 真实 MySQL+Redis 起 API（DB_URL/REDIS_URL 指真实库）。
2. 建客户/项目/需求单，上传 1 张产品图 → asset_id。
3. `POST /projects/{id}/generate`，body：`{subscene:S1, family:family_4, tier:standard, category:食品, style:清新自然, width:1024,height:1024, n:1, asset_ids:[asset_id]}`（有素材 → pipeline 走 EDIT）。
4. 观察：约 180s 后返回 200，但 `used_model=seedream-5`、`url=mock://seedream-5/0.png`。

## 期望 vs 实际
- 期望：图生图 edit 真实返回 `used_model=gpt-image-2` + `file://` 真实图（与 text2img 一致，秒级~分钟级）。
- 实际：edit 请求 180s 超时 → 回落 mock，主业务保真链路不可用，且对调用方"成功 200"**静默降级**。

## 环境 / 上下文
- 中转站：apinebula.com/v1，model=gpt-image-2-vip，provider `trust_env=False`（已绕过本机 SOCKS）。
- text2img 同站同模型同 key 64.5s 成功 → 排除连通/鉴权/网络；指向 `/images/edits` 多部分请求
  （疑点：multipart 字段约定 / image 尺寸·mime / 该中转站对 edit 端点的支持或排队）。
- 影响面：PRD 图生图保真为主业务（参 memory「图生图保真靠 /images/edits」），P1。

## 待开发排查方向（建议）
1. 直连 `curl -F` 打中转站 `/images/edits`（短超时）复现，拿原始 HTTP 行为（卡连接？卡响应？4xx？）。
2. 核对 edit multipart 是否需额外字段（如 `response_format`、`image[]` 数组、mask、square/png 限制）。
3. 超时与"静默降级"策略评估：edit 主链路超时是否应直接上抛而非静默回落 mock（避免假成功）。

## 处理记录
- 2026-06-02 [QA] E2E 集成验证发现：edit 真实调用 180s 超时回落 mock，text2img 真实成功。已带证据开单，owner→开发。状态=待复现。
