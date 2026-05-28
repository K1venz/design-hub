---
id: ISSUE-0002
title: M3-a failover/中转 adapter 与 spec 决策不一致（错误切换/预算口径/质量档）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: PM
owner: 开发
created: 2026-05-28
updated: 2026-05-28
related:
  - spec: docs/superpowers/specs/2026-05-28-gpt-image-2-failover-relay-design.md (commit b4c61ca)
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py
  - code: image-code/src/design_hub/infrastructure/providers/failover.py
  - commit: fe1e77b feat(M3-a)
---

## 现象
M3-a (fe1e77b) 已实现 `OpenAICompatImageProvider` + `FailoverModelProvider`，但实现早于产品决策定稿，与 spec（b4c61ca）确认的两条决策及成本约束有 3 处不一致。

## 偏差明细

### ① 错误切换策略未落实（决策①）—— openai_compat.py
`generate()` 用 `response.raise_for_status()`，把**所有** 4xx/5xx 经 `httpx.HTTPError` 统一映射为 `ProviderError`。
- 后果：400/422（提示词违规、参数非法）也会触发 failover 去切备用中转。同一坏 payload 在备用站必然同样失败 → 白烧一次调用 + 拖延，违反 fail-fast。
- 期望（spec §3.1 错误映射表）：
  - 连接错误 / 读超时 / 429 / 5xx → `ProviderTimeout`（可重试，切备）
  - 400 / 422 → `DomainError`（立即上抛，**不切备**）
  - 2xx 响应体非法 → `ProviderError`（视为该家故障，切备）
- 实现要点：需按 `httpx.HTTPStatusError` 的 `response.status_code` 分流，不能一把 `HTTPError` 全归 `ProviderError`。

### ② 预算预留口径错误（决策②）—— failover.py
当前 `self.unit_cost = providers[0].unit_cost`（取主用价）。
- 后果：真切到更贵的备用中转时，`CostEstimator/CostGuard` 预留不足，可能击穿预算红线。
- 期望（spec §3.3）：`self.unit_cost = max(p.unit_cost for p in providers)`，保守预留、按实际出图家结算。
- 附：建议补 `assert all(p.name == providers[0].name for p in providers)`，确保只有同模型中转互备（spec §3.2）。

### ③ 质量档缺失 + b64 取 url 隐患 —— openai_compat.py
- payload 未带 `quality`：gpt-image-2 不指定质量可能默认走最贵档（≈¥1.5/张），与成本约束冲突。spec §6 已列为开放项——最小处理：`OpenAICompatImageProvider` 构造期固定 `quality`（默认 medium）。
- `response_format:"url"` + `item.get("url")` 为空即报错：gpt-image 原生协议返回 `b64_json` 而非 url，除非中转站代转 url，否则会失败到两家全挂。需按选定中转站（诗云/API易）实际返回确认，必要时支持 `b64_json` 解码。代码现有自注 "b64 handling TBD with chosen gateway" 即指此。

## 期望 vs 实际
- 期望：实现严格对齐 spec（b4c61ca）的决策①②与 §6 最小处理。
- 实际：①②未落实，③留有 TBD。

## 环境 / 上下文
- 路线已定：「gpt-image-2 + 合规」，主备均用能开增值税票的中转（诗云主 / API易备），单张成本不卡 1-3 毛。
- 主备顺序由 composition.py 配置决定（OCP），拿到 key 小额实测后把更稳+更便宜者设为 relays[0]。

## 处理记录
- 2026-05-28 [PM] 创建并确认（读 fe1e77b 代码核对 spec），状态=已确认，owner=开发
