---
id: ISSUE-0044
title: 请求体未知字段被 pydantic 静默忽略——应统一 extra=forbid（fail-fast）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P3          # 非功能 bug（产物正确），是 fail-fast 洁癖 + 误用静默无反馈的困惑面
reporter: QA（复刻边界回归发现 overlay_texts 传 /clone 被静默忽略）
owner: 开发
created: 2026-06-10
related:
  - code: image-code/src/design_hub/interface/listing_schemas.py（CloneRequest/ListingGenerateRequest 等请求体未设 model_config extra=forbid）
  - 群聊: #567（QA 发现）/#568（dev 判 backlog 统一收）
---

## 现象
QA 复刻边界回归：给 `POST /listing/clone` 传 `overlay_texts`（CloneRequest 无此字段）→ **不报错**，被 pydantic 默认 `extra=ignore` 静默吞，请求照常处理（产物无图上文案=功能正确）。

## 判断
- **非功能 bug**：overlay_texts 对复刻无影响、产物正确（「overlay 不进复刻流」满足）。
- **是 fail-fast 缺口**：未知字段静默忽略 = 用户/前端误发字段时「没效果也不报错」的困惑面（dev #568 认同不止洁癖）。按本仓 fail-fast 文化应 `extra=forbid` → 422。

## 决议（dev #568）
- **本轮不收**：改 schema 行为会让 QA 复刻边界矩阵 13/13 重跑（未知字段全变 422），且应**统一收**（所有请求体 CloneRequest/ListingGenerateRequest/CustomerCreate… 一起 forbid、口径一致），单收 /clone 反造成不一致。
- **backlog**：「请求体统一 `extra=forbid`」，下轮小杂项窗口做 = dev 一行/基类 model_config + QA 一次回归（各端点补「未知字段→422」维度）。

## 待办
- [ ] dev：请求体基类/各 schema 统一 `model_config = ConfigDict(extra="forbid")`。
- [ ] QA：回归补「未知字段→422」维度（clone/listing/customer 等），更新 clone_boundary 的 overlay 用例断言 404→422。

## 处理记录
- 2026-06-10 [QA] 复刻边界回归发现 overlay_texts 静默忽略（#567）。dev #568 判非本轮、统一收进 backlog。开本条 P3、owner=dev，待下轮小杂项窗口。
