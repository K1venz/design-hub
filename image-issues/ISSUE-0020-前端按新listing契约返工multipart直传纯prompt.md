---
id: ISSUE-0020
title: 前端出图工作台按新 listing 契约返工（multipart 直传 + 纯 prompt 直出）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 开发
owner: 前端           # 球在前端：按新契约改 v2 设计与实现
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md
  - code: image-web/docs/出图工作台-v2-商品套图重做-设计.md
  - issue: ISSUE-0019（自由 prompt；本链路升级为核心入参）
---

## 背景
用户拍板 listing 一键出图走「**multipart 直传 + 纯用户 prompt 直出（提示词唯一杠杆）**」轻量链路，
后端设计见上方 spec。这取代了前端 v2 设计稿（`出图工作台-v2-商品套图重做-设计.md`）里几处分叉契约，
前端需返工对齐。后端会另起 `POST /listing/generate` 链路（不复用 /generate/async + project）。

## 需前端调整（对照 v2 设计稿）
1. **图片传输**：`asset_ids`（资产库）→ **multipart 直传 ≤3 张**。
   **删除"从资产库选"(AssetPickerInline)**——本链路不持久化素材、不支持图库复用（用户已确认接受）。
2. **删除 category、style 下拉**（用户拍板删除；后端编排器不参与本链路）。
3. **出图端点改对接**：
   - `POST /listing/generate`（multipart/form-data，Bearer）→ 返回 `{job_id}`。
   - `GET /listing/{job_id}/events?access_token=<jwt>`（SSE，逐张到达，沿用 ISSUE-0011 query 鉴权）。
4. **请求字段**（与 spec §4 一致）：
   - `images`: file × (1..3)
   - `prompt`: str（"商品卖点&要求"文本框 = 用户自由 prompt，本链路核心入参，落实 ISSUE-0019 第1点）
   - `ratio`: str（如 "1:1"，后端映射 size；前端"尺寸/比例并存"中**尺寸不再单独传**，由 ratio 决定）
   - `n`: int 1..7（"张数"下拉）
   - `modifiers`: JSON 字符串，通用 key→value 袋子，如 `{"platform":"亚马逊","region":"美国","language":"英文"}`
     —— **增删下拉只改这里的 key，契约不变**。
5. **不再需要**：`subscene/family/tier/asset_ids/project/快速任务（隐式建项目）` 在本链路全部去除。

## 期望 vs 实际
- 期望：前端按 `/listing/*` 新契约提交 multipart + prompt + modifiers，SSE 逐张渲染候选。
- 实际：现 v2 设计稿基于 asset_ids + project + category/style + /generate/async，需返工。

## 环境 / 上下文
- 下拉**完整枚举**（平台/国家地区/语言/比例的取值）由 PM 出（见 ISSUE-0021），前端按枚举渲染。
- 后端 `/listing/*` 实现进度见 image-code；契约以 spec §4 为准，落地前可先搭骨架。

## 处理记录
- 2026-06-04 [开发] 创建并派给前端；契约见 spec §4，背景见 spec §2(0a/0b)/§8。状态=已确认，owner=前端
