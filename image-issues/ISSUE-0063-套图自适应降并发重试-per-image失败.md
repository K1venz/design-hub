---
id: ISSUE-0063
title: 套图自适应降并发重试——per-image 429 失败时动态降并发（新 key 分组限流更紧）
status: 挂起          # backlog：当前静态 LISTING_CONCURRENCY=1 已稳，非阻断，择机做
severity: P3
reporter: 开发        # coordinator #1094 观察 + 建议记 backlog
owner: 开发
created: 2026-07-08
updated: 2026-07-08
related:
  - code: image-code/src/design_hub/application/listing/listing_service.py（并发 Semaphore）
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py（provider 层 429 重试）
  - issue: ISSUE-0047（套图并发打满 429=静态 concurrency 缓解）
  - issue: ISSUE-0056（备用渠道切换）
---

## 现象 / 背景
apinebula 换 gpt-image-2-1k 分组新令牌后，**新 key 分组并发限流比旧 key 紧**
（coordinator #1094 实测）：
- 并发 3 → 套图 2/5 失败；
- 并发 2 → 仍 3/5 失败；
- 并发 1（串行）→ 稳，但慢。
当前缓解=静态 `LISTING_CONCURRENCY=1`（ops env 可调，ISSUE-0047 机制），稳但牺牲吞吐。

## 期望 vs 实际
- 期望：套图在不同 key 分组限流档下**自适应**——限流紧则自动降并发保成功率、限流松则升回吞吐，
  无需 ops 手调 env、无需为最紧档常驻串行。
- 实际：并发档是静态配置，须人肉按分组档位调；调紧了牺牲吞吐、调松了掉图。

## 设计方向（backlog，实现前复核）
provider 层已有 429 抖动退避重试（ISSUE-0047/0055）——治**单请求**瞬时限流；本条治
**套图批的并发面**：
1. **service 层自适应并发**（AIMD 式）：套图批内若累计 per-image 429 达阈值 → 收缩有效
   并发（信号量降档）跑后续/重试失败张；连续成功 → 缓升回上限。落在
   `ListingGenerationService` 的 Semaphore 调度，不碰 provider。
2. 或**失败张末轮串行补跑**：批主体按 `LISTING_CONCURRENCY` 跑，收尾把失败张以并发=1 补一轮
   （实现更简、无常驻状态）。
两者都须保：成本口径不变（成功张计费、ISSUE-0045）、fail-closed 语义不变、单图流 n=1 不回归。

## 升级备选（需用户拍，非本条）
若串行仍抖：apinebula **image2-vip 分组**（文档载，档位或更高）——属渠道/成本决策，用户拍，
经 0057 配置页加渠道即可，与本条码改正交。

## 处理记录
- 2026-07-08 [开发] coordinator #1094 出图恢复实测新 key 分组限流更紧、建议记 backlog；
  开条登记设计方向。当前 LISTING_CONCURRENCY=1 已稳、非阻断 → status=挂起(backlog)，
  待吞吐成为痛点或多渠道并用时再择机实现。
