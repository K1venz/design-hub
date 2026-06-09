---
id: ISSUE-0040
title: listing 二次编辑 — 基于已生成结果 + 新提示词迭代再生成（缺失核心能力）
status: 已确认        # 需求已确认存在、待团队设计 + PM 排期；非 bug，借状态机表「已确认=确认要做」
severity: P1          # 缺失核心能力、用户已勾选要做；最终优先级随用户拍
reporter: PM          # coordinator 审计 backlog + 用户提出（群聊 #394），PM 接需求
owner: PM             # PM 持球：开 PRD 草稿 + 收口设计 → 排期与验收标准；设计 scope 由 coordinator 拉 prompt/dev/frontend
created: 2026-06-09
updated: 2026-06-09
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
> gating 已解除 → PRD §3.12.13 已定稿（验收标准 + 落地分工）。下一步 = PM 牵头四方设计三方对（对齐 Q1–Q7 + edit_mode/source_image_id 契约）→ **schema 变更经用户签字** → 实现。

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
