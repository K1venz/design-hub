---
id: ISSUE-0045
title: provider 信任上游返回张数：n=1 可落 2 图并双计费（资损向）
status: 待验证
severity: P1
reporter: 开发        # 现象由 frontend-b 在 UI 自测中发现（#675），dev 代码定根因
owner: QA
created: 2026-06-11
updated: 2026-06-11
related:
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py
  - test: image-code/tests/test_provider_contract.py
  - chat: "#675 现象 / #676 QA lead / dev 诊断与修复"
---

## 现象
旧 qa 容器（0040 重建前）：单图流 n=1 一次 POST /listing/generate，落库 2 张
listing_image、job 计费 ¥0.80（2×0.40）。job=`830acc08d4e8435f97e8956b8cf18a5a`，
前端单击一次、单 job_id，已排除双发。

## 根因（代码级确认）
`OpenAICompatImageProvider._parse` 对响应 `data[]` 逐项建图、每项计一次
unit_cost，**完全信任上游返回条数、无 n==len(data) 契约核**。中转站对 n=1
返 2 条 data → 落 2 图、计 2 份，且 `guard.reconcile(reserved=0.40,
actual=0.80)` 向上调账，把上游违约放大成用户侧资损。

排除项（代码证据）：
- 重试双成功 ≠ 本现象：重试只在超时/瞬时 5xx 后发生且旧 response 整体丢弃，
  仅成功那一次进 `_parse`——两次尝试的产物不可能合并入库（重试双成功只可能
  在中转站侧多扣真实费用，对我们的 DB 不可见）。
- 命令重执行 ≠ 本现象：listing_job.id 为主键，二次 record 必 IntegrityError
  整体回滚，库内不可能出现"1 行 job + 跨次执行累积的图"。
- 因此唯一与 DB 状态一致的通路：**单次响应 data[] 含 2 项**。可由该 job 两行
  图的 seed 佐证（`_parse` 按枚举赋 seed）：预测恰为 0 和 1。

## 期望 vs 实际
- 期望：返回张数 != 请求 n → I/O 契约违约，fail-fast（ProviderError），
  guard 回滚预扣，不落图不计费。
- 实际：多返多落多计费、少返静默缺图。

## 修复
`_parse` 增加 expected_n 契约核（f0041fa 之后提交）：
`len(data) != expected_n → ProviderError`；全代码路径现行恒以 n=1 调用
（单图并发循环/套图/复刻/二次编辑），严格相等核安全。
回归测试 tests/test_provider_contract.py 2 例（mismatch 拒 / 恰好计 1 份）。

## 待验证（QA）
1. 旧 job 取证：`SELECT seed, image_key, cost, status FROM listing_image
   WHERE job_id='830acc08d4e8435f97e8956b8cf18a5a' ORDER BY seed;`
   —— 预测 seed=0,1 两行（单响应双项实锤）；image_key 是否相同可看出中转站
   是「同图双计」还是「真出两图」。
2. 修复版部署 qa 后：n=1 探针（QA #676 已计划）确认不再复现；若中转站再次
   多返，期望整单 TASK_FAILED + 零计费（预扣已回滚）。

## 处理记录
- 2026-06-11 [frontend-b] UI 自测发现 n=1 双图双计费（#675），怀疑 provider 重试或任务重执行
- 2026-06-11 [QA] 当真，给出 retry 非幂等 lead，承诺 edit_real 顺手盯 + n=1 探针（#676）
- 2026-06-11 [开发] 代码定根因：_parse 无 n 契约核；证伪 retry/重执行两条 lead；修复+回归测试入库；状态→待验证，owner=QA
