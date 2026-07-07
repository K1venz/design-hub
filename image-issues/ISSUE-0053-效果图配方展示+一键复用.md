---
id: ISSUE-0053
title: 效果图「配方展示 + 一键复用」——展示可复用配方（非内部卡 prompt）+ 一键预填出同款
status: 修复中        # spec 定稿派单、dev+frontend-b 并行开工中（feature 走 issue 生命周期）
severity: P1          # 用户直接提需求；获客/复用闭环（成果区做同款 + 历史复用配置）
reporter: PM          # 用户提需求（coordinator #971 转达），spec 定稿 ec9e80a，PM 入档
owner: 开发+frontend-b # 并行：dev 落点B后端(recipe字段+prod只读回填)、frontend-b 落点A+B UI+预填机制
created: 2026-07-07
updated: 2026-07-07
related:
  - PRD: §3.15 效果图配方展示 + 一键复用
  - spec: docs/superpowers/specs/2026-07-07-recipe-reuse-design.md（coordinator 定稿 ec9e80a）
  - issue: ISSUE-0048（新公开首页/成果区=落点 B 宿主）、§3.14 ④成果区（GET /showcase 13 张）
  - code: image-code showcase（ShowcaseEntry/GET /showcase）、listing 历史（GET /listing/jobs/{id} ListingJobDetailOut）；image-web /set + workbench-store
  - 群聊: image-gen#1 #971（coordinator 派单）
---

## 定性（用户提需求 2026-07-07，coordinator #971 转达）
效果图展示里做**提示词复用**：展示图片的同时展示**生成配置与提示词**，可**一键复用出同款**。spec 定稿入库、coordinator 派单。

## ✅ 核心口径（铁律·本条最重要）
展示与复用的对象 = **「配方」= 用户可复用输入**：图型（白底/场景/卖点）配比、比例、张数、平台、风格描述（`listing_job.prompt`=用户自由文本）、卖点文案、modifiers。
**绝不展示组装后的完整内部卡 prompt**，三个硬理由：
1. **根本没存**——`listing_job.prompt` 只存用户自由文本，卡体系组装的完整 prompt 用完即弃（读码实锤）；
2. 卡体系 = **核心商业资产**（"提示词是唯一质量杠杆"），公开展示 = 泄漏给竞品；
3. 产品**无完整 prompt 输入口**（prompt 恒走卡链），展示了也无法复用 → **展示配方才是可复用闭环**。

## 两个落点
- **A. 出图历史（自己的图）——纯前端、数据已齐、后端零改**：`GET /listing/jobs/{id}`（ListingJobDetailOut）已回吐 prompt/modifiers/platform/ratio/size/n/每张 image_type/clone_mode/edit_mode。UI=历史详情页「查看配方」抽屉（图型配比/比例/风格描述/文案/平台/风格参数 + 复刻·编辑单模式徽标）+ **「复用配置出图」→ 跳 `/set` 预填**；工作台结果卡同给「复用配置」入口（同一详情数据源）。
- **B. 首页成果展示区（公开获客）——小后端 + 前端**：`ShowcaseEntry` 扩 `recipe` 字段（styling 摘要/ratio/图型/文案要点），值从 prod 那 5 单真实 job **只读回填**、人工写死进静态清单（**零迁移零建表**）；`GET /showcase` 响应加 recipe、依旧无鉴权无用户数据。UI=展示卡 hover/点开显配方 + **「做同款」→ 未登录跳登录墙 → 回跳携配方 → `/set` 预填**。

## 预填机制（前端契约）
`navigate('/set', { state: { prefill: {...} } })` + workbench-store 加 `applyPrefill(prefill)`（覆盖 config/styling/文案，**不带 uploads**——产品图必须用户自己传，**配方≠素材**）；登录墙回跳复用现有 `location.state.from`，prefill 挂同一 state 随行；预填后用户可改任何项再生成——**配方是起点不是锁定**。

## 验收标准（QA，照 spec §五）
1. 历史详情/结果卡可看配方，「复用配置」到 /set 各项预填正确（图型配比/比例/风格描述/文案）。
2. showcase 卡配方展示；未登录点「做同款」→ 登录 → 回跳 /set 预填不丢。
3. 任何响应/界面**不出现内部卡 prompt 内容**（口径①·核心资产不外泄）。
4. 预填不带 uploads；用户改动预填项后生成按改后值走。
5. 老工作台/历史/showcase 零回归。

## 范围外（YAGNI，二期）
chat 结果卡配方入口（后续小补）/ 配方分享链接·配方库 / 复刻·编辑单的「复用」（仅展示配方徽标、复用按钮只做套图单）/ overlay 文案逐张映射（展示 job 级要点即可）。

## 处理记录
- 2026-07-07 [PM] 用户提需求（coordinator #971 转达，spec 定稿 ec9e80a）→ PM 入档：落 PRD §3.15 + 开本条。
  **核心口径入档=展示「配方」非内部卡 prompt**（没存·核心资产不外泄·展示了也复用不了 → 展示配方才是可复用闭环）。
  分工（并行，写域不相交）：dev 落点 B 后端（ShowcaseEntry+recipe·prod 只读回填 5 单·零迁移零建表·历史侧确认零改）；
  frontend-b 落点 A+B UI + /set 预填机制（applyPrefill 不带 uploads·配方≠素材）+ codegen；QA 验收 5 条；
  部署=deploy.sh(showcase 后端)+push.sh **零迁移轮**（coordinator 编排）。**仍内测灰度**（7.B/7.A 前置不变）。
  status=修复中、owner=开发+frontend-b（并行开工）。**排队顺延**：移动端适配/chat P3/0052/0050 顺延本条后，真实用户 bug 仍随时打断。
