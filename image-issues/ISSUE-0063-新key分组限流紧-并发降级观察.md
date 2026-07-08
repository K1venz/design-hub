---
id: ISSUE-0063
title: gpt-image-2-1k 新令牌分组限流比旧紧——已调串行 mitigation；image2-vip 升级待用户 + 自动降并发 backlog
status: 已确认        # coordinator 出图恢复后观察实测(并发3→2/5失败·并发2→3/5失败)；已调 LISTING_CONCURRENCY=1 串行止血
severity: P2          # 影响出图吞吐(串行=稳但慢)；非资损非阻断(串行下能出图)；真实用户高峰或体感慢
reporter: coordinator  # ISSUE-0056 出图恢复后新 key 实测发现（#1094）
owner: PM             # 排优先级 + image2-vip 升级=用户决策(档位/成本)待拍；自动降并发=dev backlog
created: 2026-07-08
updated: 2026-07-08
related:
  - issue: ISSUE-0056（apinebula key 恢复=本观察来源，新分组令牌 gpt-image-2-1k）、ISSUE-0047（套图并发/429 退避）、ISSUE-0055（失败人话+墙钟，已让失败干脆）
  - 群聊: image-gen#1 #1094（出图恢复实证 + 新 key 限流观察）
---

## 观察（coordinator #1094，出图恢复后实测）
用户提供的 **gpt-image-2-1k 分组新令牌** 限流比旧 key 紧：
- **并发 3 → 2/5 失败**；**并发 2 → 仍 3/5 失败**。
- coordinator 已调 **`LISTING_CONCURRENCY=1`（串行）止血**——稳但慢（吞吐降）。0055 修法已让失败张人话+不全灭+按成功计费（体验兜底在）。

## ⚠️ 治本升级（coordinator #1101）：转异步 = ISSUE-0065
串行也挨限流（品类批终态全 1/3、prod 真实用户成功率 ~33%）→ coordinator 实证**异步接口 image-tasks 30s completed 零失败**=治本 → **ISSUE-0065（AsyncImageTasksProvider，P1）**。本条（0063）的串行 mitigation / image2-vip 升级 = **stopgap**，真正的解是 0065 转异步；image2-vip 仅在异步也不够时才评估。

## 处置（三层）
1. **✅ 已止血（coordinator）**：`LISTING_CONCURRENCY=1` 串行，当前出图稳定（品类真图批串行跑 4×n3≈¥4.8）。
2. **⏸️ 升级选项 = 待用户拍**：apinebula **image2-vip 分组**（官方文档有、档位可能更高、放开并发）——**换更高档位=成本/档位决策，需用户拍**。触发条件=串行仍抖 / 真实用户高峰体感慢。PM 已向用户点明选项。
3. **📋 dev backlog → ISSUE-0064**：**per-image 失败自动降并发重试**（失败张探测到限流→自动降 concurrency 重试该张，而非整批串行；比手动调 env 更弹性）——dev 已开 **ISSUE-0064**（套图自适应降并发重试，P3 挂起、方向=service 层 AIMD 自适应并发 / 失败张末轮串行补跑，待吞吐成痛点再做）。本条（0063）=限流观察+串行 mitigation+image2-vip 用户决策；0064=dev 实现 backlog，一号一条。

## 验收标准（若做升级/backlog）
- 升级 image2-vip 后：恢复并发（如 3）不再高失败率、吞吐回升、成本在预算。
- 自动降并发 backlog：限流场景自动降级重试成功、不需手动调 env、不牺牲正常吞吐。

## 范围外（YAGNI）
多中转站负载均衡（0057 备用渠道切换是手动侧的解）/ 复杂重试编排框架。

## 处理记录
- 2026-07-08 [coordinator+PM] 出图恢复（ISSUE-0056）后新 key 分组限流紧实测（#1094）→ PM 开条挂账：
  已止血=`LISTING_CONCURRENCY=1` 串行（coordinator）；**image2-vip 升级=用户决策待拍**（PM 已点用户，触发=串行仍抖/高峰慢）；**per-image 自动降并发重试=dev backlog → ISSUE-0064**。
  定级 P2（影响吞吐、非资损非阻断、串行下能出图、0055 失败兜底在）。**排期**：非阻断，image2-vip 待用户拍才动、backlog（ISSUE-0064）待 dev 空档。owner=PM（跟用户决策+backlog 排期）。真实用户高峰体感慢=升级触发信号，QA/coordinator 观察。
- 2026-07-08 [PM] **撞号交叉链修正（dev-1 #1097）**：本条 0063 与 dev 同时开的 0063 全局计数器 race 撞号；dev 让路、把「套图自适应降并发重试」改号 **ISSUE-0064**（related 指回本条）。本条（0063）=PM 观察/串行 mitigation/image2-vip 用户决策；0064=dev 实现 backlog，一号一条干净。**image2-vip 升级实现路径**（dev #1095 标）：走 0057 配置页加渠道、与码改正交（无需码改、admin 配置即可）——即用户拍 vip 后，在配置页加 image2-vip 渠道+设默认即生效。
