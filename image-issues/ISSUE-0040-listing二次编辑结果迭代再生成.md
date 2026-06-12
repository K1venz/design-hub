---
id: ISSUE-0040
title: listing 二次编辑 — 基于已生成结果 + 新提示词迭代再生成（缺失核心能力）
status: 已关闭        # PM 终验收：2026-06-11 prod 上线 + smoke 5/5 + demo 全链验通，闭环
severity: P1          # 缺失核心能力、用户已勾选要做；最终优先级随用户拍
reporter: PM          # coordinator 审计 backlog + 用户提出（群聊 #394），PM 接需求
owner: PM             # PM 持球：开 PRD 草稿 + 收口设计 → 排期与验收标准；设计 scope 由 coordinator 拉 prompt/dev/frontend
created: 2026-06-09
updated: 2026-06-12
related:
  - PRD: §3.12（listing 一键出图主线）；待新增 §3.12.13（二次编辑）
  - code: image-code 后端已有 /images/edits 图生图能力（但无 listing「基于结果再编辑」流）
  - issue: ISSUE-0039（旧流 X-User-Id 越权归属教训 → 迭代链 owner 隔离要对齐 Bearer）
  - 群聊: image-gen#1 #394（coordinator 审计确认缺失 + 用户勾选）、#395（QA 备用例骨架）、#400/#404（prompt 编辑模式组装设计点）
---

## 设计团队（coordinator 拉齐，#401/#406）
PM(PRD + 排期/验收) · **prompt(编辑模式保真块 / 组装规则)** · dev(/images/edits 接线 + 迭代链) · frontend-b(结果区「基于此图再编辑」入口) · QA(迭代链 owner 隔离 + 二次保真不崩)。

## ✅ 交互模型（用户已拍 2026-06-09 / coordinator #413：delta + full 两种都要）
→ prompt `compose_prompt` 加 `edit_mode ∈ {delta, full}` 模式分支：
- **delta（微调，默认）**：增量改动指令（「背景换厨房 / 花生再多点 / 光更暖」）→ 锁产品+品牌文字 + **沿用上一版构图基底** + 只 apply delta。**ratio/category 继承父 job**、prompt/modifiers 叠新。
- **full（重做）**：全新场景需求 → 以上一版结果作保真锚 + 全新场景重绘。**ratio/category 可改**。
> gating 已解除 → PRD §3.12.13 已定稿（验收标准 + 落地分工）。**schema 三列（parent_job_id/source_image_key/edit_mode）已经用户签字、随套图迁移上线 prod → 实现前置解除**（新列出现再亲签，实际零新迁移）。设计三方对 2026-06-11 启动并当日终局（四方 ACK 零开放项）→ 实现 → **2026-06-11 prod 上线 + smoke 5/5 + demo 全链验通 → 已关闭**。

## 需求
listing 当前只能「从头传图 → 一键出图」，**无法基于一次生成的结果 + 新提示词迭代再生成**。
用户提出：拿生成结果当输入，叠加新 prompt 再生成一次/多次（迭代式精修），而不是每次都从原始素材重来。
coordinator 审计 backlog 确认这是**缺失功能**（后端有 /images/edits 图生图底座，但没有 listing 的「基于结果再编辑」业务流）。

## 待团队设计确认的点（PM 预判，挂此供 coordinator 拉 prompt/dev/frontend scope）
1. **迭代入参**：上一轮 job 产物的 `image_key` + 新 prompt → 走 `/images/edits` 图生图（复用 listing 现有 gpt-image-2 edits 链路）。
2. **成本计次**：每次迭代 = 一次真实出图 → 入 `cost_ledger`、计入预算守门（不能因「是编辑」就免计）。
3. **迭代链 owner 隔离（安全，重）**：只能基于**自己**的 job 迭代；拦截基于他人 job 迭代。身份用 Bearer（`CurrentUserDep`），**别重蹈 ISSUE-0039**（可伪造 X-User-Id 越权归属）。
4. **历史链结构**：迭代记录挂同一 `listing_job` 下按轮次组织，还是新 job + `parent_job_id` 链？影响历史页展示与「基于哪张迭代」的可追溯。
5. **保真块**：迭代仍走通用产品保真块（§3.12.11），新 prompt 叠加在 styling 层（对齐路线 A：用户 prompt 兜底 styling）。
6. **前端形态**：历史页/结果页加「在此结果上继续编辑」入口，带上一轮 prompt 预填可改。

## Q1–Q7 PM 初拍（QA 用例骨架 #407 提出，已落 PRD §3.12.13 草稿；设计三方对与 dev/prompt 最终确认）
- **Q1 入口契约** → **独立 `source_image_id`（结果图稳定 id）**，后端由它解析 owner+image_key+父 job；不让客户端拼 `parent_job_id+image_index`（消越界/畸形校验面、owner 直命中记录 user_id）。字段名 dev 按持久化模型定。
- **Q2 源图来源** → 后端用 **image_key 从 TOS generate 桶取对象**（服务端凭证即时签/直读），不依赖客户端可能过期的签名 url（对齐 ISSUE-0034）。
- **Q3 迭代深度/分叉** → **无硬深度上限、允许多次分叉**（每次独立 job+计费，成本由既有预算闸守，YAGNI）。累积失真是质量风险（TC-05）非契约限制。
- **Q4 参数继承** → **已定稿**（用户批 delta+full）：delta 模式 ratio/category **继承父 job**（换比例=重构图≠编辑）、prompt/modifiers 叠新；full 模式 ratio/category 可改。
- **Q5 成本口径** → ledger **按次单计**；UI 展示**单次 + 迭代链累计**（用户面口径 coordinator 从用户确认）。
- **Q6 落桶+job 关系** → 新图落 **generate 桶**；每次二次编辑 = **独立新 job + `parent_job_id` 父指针**（独立 cost/SSE/status、parent 链表谱系、支持分叉），复用现有 job/SSE/计费机制、对其他接口零改造。
- **Q7 历史展示** → 按 parent 链组织（MVP 线性链、分叉树展示作增强），归 frontend，PM 给方向。
> ⚠️ Q1/Q6 引入 `source_image_id`/`parent_job_id` = schema 变更 → **dev 动手前须经用户签字**（DB 变更先征求用户，铁律）。

## QA 预备（#395）
迭代功能一旦做，QA 覆盖：① 迭代链 owner 隔离；② 二次 prompt 的保真不崩；③ 成本按次计。用例骨架 QA 已备。

## 期望 vs 实际
- 期望：用户可在一次结果基础上叠新 prompt 迭代精修，链路可追溯、成本计次、owner 隔离。
- 实际：只能从头传图重来，无基于结果的迭代流。

## 处理记录
- 2026-06-09 [PM] coordinator 审计 backlog + 用户勾选（#394）→ PM 接需求，开本条占位 + 起 PRD §3.12.13 草稿。定级 P1（缺失核心能力、用户已勾），最终优先级随用户拍。owner=PM 持球收口设计 → 排期；设计 scope 待 coordinator 拉 prompt/dev/frontend，对齐后回 PM 落验收标准。**先不实现，等设计对齐。**
- 2026-06-09 [PM] **用户拍交互模型 = delta + full 两种都要**（coordinator #413）→ gating 解除。PRD §3.12.13 草稿→**定稿**（交互模型两分支 + Q4 参数继承定稿 + 验收标准 D1–D8 + 落地分工）。下一步 PM 牵头四方设计三方对（对齐 Q1–Q7 + `edit_mode`/`source_image_id` 契约）→ schema 变更（`parent_job_id`/`source_image_id`/`edit_mode`）经**用户签字**后实现。仍 owner=PM、设计阶段。
- 2026-06-11 [PM] **设计三方对启动**（coordinator #631 派棒、PM 第一棒）。前置已全齐：schema 三列已签且随套图迁移上线 prod（零新迁移预期）、QA 骨架已备（f64d365，两 P0=D1 owner 隔离 + D2 多轮累积失真 TC-05）。PM 发 §3.12.13 摘要 + 开放问题清单入群（已定 9 条不重开 + 开放 Q-α~Q-ζ：端点形态/入口 shape/delta 父 prompt 上下文/图型卡与 overlay 关系/可编辑源范围/单次张数/quality 档）。并行棒：prompt 两模式组装草案 + dev 技术方案 + frontend-b 交互（先方案不动代码）。owner=PM（牵头收敛）。
- 2026-06-11 [PM] **设计当日终局**：用户拍 3 scope（Q-γ MVP 不改图上字 / Q-δ 所有成功出图皆可编含套图张与复刻产物、失败张 404 anti-enum / Q-ε 一次 1 张）+ Q-α 瘦路由 `POST /listing/edit`、Q-ζ 默认档随 PM 倾向 + Q-β prompt 裁定（两档不带父 prompt，#645）+ D2 链根锚硬约束（每轮锚迭代链根原始产品图、绝不锚上一轮，coordinator #637 确认）+ R2（不收 category）/R5（chain_cost 根算源张单张）PM 确认。五方互锁：PRD / 第六类编辑模式卡 `d9d4f21` / dev 技术方案 `b37e109`（handle=source_image_key 案3）/ frontend 交互方案 `5e0ed50` / QA 骨架。四方 ACK 零开放项 → dev 动工放行。PRD §3.12.13 同步入档（846c93e/8ef31d8/59bed75/7fda020）。
- 2026-06-11 [开发/QA/运维] **实现 → 上线**（群 #669-#705）：dev `f0041fa`（17 文件、门禁 46 绿、卡↔code 自动闸扩 9 物化块、零新迁移）→ QA 闸① 全绿（edit_boundary **12/12** 首个 extra=forbid 端点验通 + edit_real API **11/11**：owner 三类越权 404、R1 根 3 产品图链 4 张喂入成功无需回退、chain_cost=1.60 R5 实证 + **视觉核 5/5：TE-03 三轮 delta 花生袋/文字 verbatim 漂移不叠加=链根锚命门 PASS**、TE-04 full 构图变产品锁死）→ frontend `ef2b81a` e2e（页内链式迭代闭环）→ prod 部署（捆 ISSUE-0045 一修 284ce82、迁移 no-op）→ prod smoke **5/5**（n=1 恰 1 图 / delta 出图 / parent 链 / chain_cost=0.80 / 落 prod 桶 + 链根锚视觉核）→ demo 抓出**前端 dist 漏部署**（旧 bundle 无 /edit；ops 补 rsync 即修 + 结构性防再犯 `82047c8`：push.sh 无条件 build 前端 + 部署SOP-checklist）→ coordinator prod demo 全链验通（#705）、footprint 全清 baseline 复原。
- 2026-06-12 [PM] **终验收通过 → 关闭**。验收 D1-D8 全覆盖实证（D1 owner 404 三类不可区分 / D2 三轮失真视觉核命门 PASS / D3 诉求生效 / D4 成本按次+chain_cost R5 / D5 源选择正确 / D6 SSE 一致 / D7 fail-fast）；prod demo 全链验通后用户转入实测使用与后续需求（UI 优化、0045 复测），二次编辑无异议。PRD §3.12.13 已标 ✅ 已上线 + 上线记录入档。衍生：ISSUE-0045（provider 张数契约资损，二修 05cc6b6 后已终关）。**status→已关闭**。
