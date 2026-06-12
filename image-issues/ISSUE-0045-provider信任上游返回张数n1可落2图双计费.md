---
id: ISSUE-0045
title: provider 信任上游返回张数：n=1 可落 2 图并双计费（资损向）
status: 已关闭        # coordinator 终关(#754)：二修 05cc6b6 部署 + 单测 spec 正确 + E2E 8 无回归 + prod 终验 15 次 n=1 全绿(无误判失败/¥6=15×0.40 资损消失) + footprint 全清 zhaokai 完好；over 截断静默、逐调用铁证结构不可得、spec 单测兜底
severity: P1
reporter: 开发        # 现象由 frontend-b 在 UI 自测中发现（#675），dev 代码定根因
owner: coordinator    # 已终关（coordinator 决定 #754）
created: 2026-06-11
updated: 2026-06-12
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
- 2026-06-11 [QA] **验证全绿、收 ISSUE-0045**（QA retry lead 被 dev 代码证伪、采信）：
  ① **SQL 取证坐实**（ops 代跑 #685，QA 无 dh_qa_ro 凭证）：job 830acc08 = 恰 **2 行 seed 0/1**（dev 预测一字不差）、**image_key 不同**（5cc03730 / 4cb68932）= 中转站对 n=1 **真返 2 张不同图**（非同图双计），job total_cost=0.80——单响应 data[] 含 2 项实锤。
  ② **修复版（284ce82）验证**（qa 重建捎修、ops #685）：edit_boundary 复验 **12/12**（资损修不破二次编辑契约）+ **n=1 资损探针 3/3**（`n1_anomaly_probe.py`，3 个 n=1 gen 全 status=完成/成功图=1/cost=0.40，**NEVER 2 图 + 计费=图数**、修后正常 n=1 不回归）。
  ③ **违约分支**（len≠n→ProviderError 整单失败不落图不计费）：中转站偶发不可控、E2E 不可强制触发，由 dev `test_provider_contract.py` 2 例单测（门禁 48 绿）覆盖。
  → **修复有效、零回归、根因坐实**。status→已修复、owner→coordinator（修随 0040 一把上 prod、部署后随 0040 prod smoke 一并终验 + 终关）。证据：探针 commit 00ecc56。
- 2026-06-11 [coordinator/QA] **一修(284ce82)矫枉过正、reopen**（#735 用户实测撞）：套图场景图 n=1 中转站返 2 图（over-deliver），`len!=n→ProviderError` 把**成功出图判成失败、好图被毙**（用户「但有返回图啊」）。根因=一修方向错：把 over-deliver（多返，常见 I/O 抖动）与 under-deliver（真没出图）一刀切成「不符即失败」。**QA miss 认领**：n=1 探针 3/3 只证「正常 n=1 不回归」、over-deliver 偶发没 force 到，且把违约分支甩给 dev 单测、未质疑该单测编码的 spec（mismatch→失败）对 over 本身就是错设计。**dev 对称认**：一刀切 spec 是 dev 写的、该当场拆 over/under。真实流量教育。status→修复中。
- 2026-06-11 [开发] **二修入库**（commit 05cc6b6，门禁 49 绿）：`_parse` 张数核拆两支——**over-deliver(len>n)→`data[:n]` 取前 n、按 n 计费、不失败**（出图保住 + 堵原资损：cost=n×unit 与返回 len 解耦，I/O 域优雅降级合规）；**under-deliver(len<n)→才失败**，文案友好化「出图数量不足/未返回图片，请重试」。单测 2→3 例（over 成功取1计n / under 失败 match 文案 / 恰好1张）。owner→QA 待验证。
- 2026-06-11 [QA] 探针升级 v2（commit 6be5e96）：断言改「n=1→完成+恰1图+计费=图数（over 截断不失败）」、失败标红查 reason。
- 2026-06-12 [QA] **二修验证绿、flip 已修复**（吸取一修 miss=信了错 spec 绿单测，这次先核 spec）：
  ① **核单测 spec 正确**（读 `tests/test_provider_contract.py`）：`over_deliver_truncates_and_bills_n`=over(n=1 返 2)→取前1张+cost=0.40+**不失败**；`under_deliver_fails`=真缺图才失败 ProviderError「出图数量不足」；exact→1图1份。**spec 本身对了**（对齐用户「图是好的」）。
  ② **E2E 无回归（8 个 n=1 调用全 clean）**：n=1 探针 v2 **5/5**（完成+1图+cost=0.40）+ 套图花生 plan 1/1/1 **通过**（3 n=1：分布正确、无 image_failed、cost=1.20=请求张数）→ 矫枉过正症状消失（套图不再误判失败）+ 资损消失（计费=请求张数·与返回 len 解耦）。
  ③ **honest 边界**：over-deliver 中转站偶发、这 8 次没明显 hit（此刻不多返）→ over 截断分支 **E2E 不可强制**，靠①spec-verified 单测 + **用户 prod 复测套图**（真实流量·用户撞过的场景）终验。
  → 二修方向对、E2E 无回归、单测 spec 核正确。status→已修复、owner→coordinator（随全量部署上 prod、用户复测套图 over-deliver 终验+终关）。
- 2026-06-12 [ops] **二修全量部署上 prod**（ship main HEAD 05cc6b6）：迁移前 mysqldump 备份 `/root/db-backup-20260612-171615.sql`、alembic no-op、api Recreated→Healthy（新镜像含张数核两支 `data[:expected_n]` + 「出图数量不足…请重试」）、nginx 未动、回滚镜像 `rollback-20260612-171541` 就绪；公网 `/`200·`/docs`404·`/api/listing/edit`401、FE bundle hash 不变。
- 2026-06-12 [QA] **prod over-deliver 终验绿**（coordinator #748 派：用户要 QA 代复测、不手动复测）：公网 `https://14.103.51.191` 跑 **3 单默认套图(1/2/2=5)= 15 次 n=1 真实调用**，**3/3 单全绿**——每单 完成 + 恰 5 张无失败行 + 分布 1/2/2 + 无 IMAGE_FAILED + **cost=¥2.00=5×0.40（资损核·与中转站返回 len 解耦）** + 落 prod 桶；聚合 **误判失败=0**（一修矫枉过正消失）、**总计费 ¥6.00=15×0.40**（原 0045 资损消失）。**视觉核** 15 张落盘（`image-qa/套图prod_smoke/`）：真「嘴嘴熊·高山七彩花生」产品图、保真佳、白底/场景/卖点图型对位、非空白占位。**honest 边界**：over-deliver 截断**静默**（`_parse:182` 无 log、QA 实读确认）⇒ 黑盒侧被正确处理的 over-deliver 与正常 n=1→1 **不可区分**、无法逐调用指认铁证；但用户刚在 prod 撞 over-deliver ⇒ 中转站当前在多返窗口 ⇒ 这 15 次极可能**真实经历** over-deliver、全 clean = 二修在真实条件下工作的强证据 + over 分支由 spec 单测兜底。证据：脚本 `taotu_prod_smoke.py`、落盘 `套图prod_smoke/`。→ **prod 无回归、无资损、出图真实**。owner 仍 coordinator（终关）；footprint（qa-test 号 + 3 jobs + TOS 对象）由 ops 盘点清（保 zhaokai id10/22）。
- 2026-06-12 [ops] **footprint 全清**（#752，children-first 事务删 scope=uid23+3 jobs）：测试号 `qa-taotu-prod-1781261585`(id23) + 3 套图单 + 15 listing_image + 3 listing_job_input + 3 cost_ledger(¥6.00) + TOS generate 15/upload 1。核验：app_user 回 5、listing_job 回 2、uid23 残留 0、**zhaokai id10/22 数据完好**。
- 2026-06-12 [coordinator] 🏁 **终关**（#754，owner 决定）。整轮闭环：一修 fail-fast `len!=n` 矫枉过正（用户实测撞「场景图生成失败」）→ 二修 05cc6b6（over→截断取前 n、计 n、不失败 / under→失败 + 友好文案，I/O 域优雅降级合规）→ 单测 spec 核对正确 + E2E 8 无回归 + prod 终验 15 次 n=1 全绿 + footprint 全清。**教训沉淀**：① fail-fast 也要分清 over/under——「数量不符一刀切」对 over-deliver 是错设计；② 真实使用是最后一道防线——光跑测试发现不了「测试编码了错 spec」。[QA] flip 黑板 已修复→**已关闭**。
