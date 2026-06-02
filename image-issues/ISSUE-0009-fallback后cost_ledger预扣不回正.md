---
id: ISSUE-0009
title: 出图 fallback 到更便宜模型后，cost_ledger 预扣不回正（预算账高估）
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: QA             # 已修复待 QA 复验
created: 2026-06-02
updated: 2026-06-02
related:
  - test: image-qa/2026-06-02-e2e-集成验证.md（四、落库核对）
  - code: image-code/src/design_hub/application/pipeline.py（precheck_and_reserve → _generate_with_fallback，无 reconcile）
  - code: image-code/src/design_hub/application/cost/guard.py
---

## 现象
出图前 `guard.precheck_and_reserve` 按**主模型预估**预扣 cost_ledger；当主模型（GPT_IMAGE_2，预估 1.19）
失败并 fallback 到更便宜的同档备选（seedream-5，实际 0.20）**成功**时，pipeline 无异常 → **不触发 rollback**，
也**不把预扣回正到实际成本**。结果：
- `cost_ledger` 记 **1.19**（主模型预估，从未修正）。
- `generation_job.total_cost` 记 **0.20**（实际 fallback 成本）。
→ 预算守门账（ledger）与出图实际账（generation_job/仪表盘）**分叉**，ledger 每次降级 fallback 高估 (1.19-0.20)=0.99。

## 复现步骤
1. 构造一次会 fallback 的出图（如本次：GPT edit 超时 → 回落 seedream）。
2. 查 `cost_ledger`：该 user 出现 1.19 的预扣行。
3. 查 `generation_job.total_cost`：同 job 记 0.20。
4. 两者不一致；月度预算按 ledger(高) 计，比实际花费(低) 提前触顶。

## 期望 vs 实际
- 期望：成功路径结束后，预扣按**实际使用模型成本**回正（reconcile），ledger 与 generation_job 一致。
- 实际：仅"异常→rollback / 成功→保留主模型预估"，缺降级后的回正分支 → 预算账高估。

## 环境 / 上下文
- 证据：本次 E2E，`cost_ledger`=(1.19, 0.20)，对应 generation_job 实际 (0.20 mock-fallback, 0.20 seedream)。
- 非数据丢失、不阻断出图，预算偏保守（高估）→ P2。但会让设计师/项目"虚假更早触顶预算"。

## 处理记录
- 2026-06-02 [QA] E2E 落库核对发现 fallback 后 ledger 预扣未回正，与 generation_job 实际成本分叉。开单，owner→开发。状态=待复现。
- 2026-06-02 [开发] 已修：`CostGuard.reconcile(reserved, actual)` 在成功路径按实际成本补一笔差额
  (append-only)，`pipeline.run` 在 `_generate_with_fallback` 成功后调用，使 ledger 净额=实际成本。
  覆盖同步+异步(worker 也走 pipeline.run)。smoke 验证:family_4/standard 主 GPT(预扣1.19) mock 失败
  →fallback seedream(0.20) 成功后 ledger 由 1.19 回正到 **0.20**;正常路径(GPT 成功)预估==实际==1.19
  不双扣。ruff+mypy(160) 绿。状态→待验证, owner→QA。
  改动: application/cost/guard.py(+reconcile)、application/pipeline.py(成功后 reconcile)。
