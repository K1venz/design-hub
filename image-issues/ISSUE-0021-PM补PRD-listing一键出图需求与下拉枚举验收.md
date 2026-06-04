---
id: ISSUE-0021
title: PM 补 PRD——listing 一键出图需求 + 下拉枚举 + 验收标准
status: 已确认
severity: P2
reporter: 开发
owner: PM             # 球在 PM：补需求、定枚举与验收
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md
  - PRD: §3.1 / §3.2 / §3.4
  - issue: ISSUE-0020（前端）/ ISSUE-0022（image-prompt）
---

## 背景
用户拍板新增「电商 listing 一键出图」轻量链路（multipart 直传 + 纯 prompt 直出），
后端设计见上方 spec。该功能当前**不在 PRD**，需 PM 补需求并给出可落地的枚举/限额/验收。

## 需 PM 决策 / 产出
1. **PRD 补章**：把 listing 一键出图写进 PRD（输入≤3图 + 下拉 + 自由 prompt + 张数 → gpt-image-2 直出 N 张候选）。
2. **标注 PRD 脱节**：§3.1/§3.2 的「BiRefNet 抠图 + 两阶段合成」已被用户拍板的"不抠图、gpt-image-2 直出、
   提示词唯一杠杆"取代，请在 PRD 标注现状，避免后人误读。
3. **下拉完整枚举**（前端 ISSUE-0020 + image-prompt ISSUE-0022 都等这个）：
   - 电商平台：亚马逊 / 淘宝 / TikTok / 独立站 / …？
   - 国家地区：覆盖哪些？
   - 语言：中文 / 英文 / …？
   - 比例：支持哪几个（注：gpt-image-2 实际只支持 1024x1024 / 1024x1536 / 1536x1024 三种尺寸，
     非方形比例需归并到这三种之一，请定映射策略）。
4. **限额**：张数上限（spec 暂定 1..7）确认；单用户/单次成本红线。
5. **验收标准**：本功能 QA 验收口径（成功率/时延/成本/错误处理），供 QA 出用例（另会派给 QA）。
6. **镜头分型是否排期**：主图白底/特写/场景/卖点图/尺寸/生活方式/对比图——MVP 不做，是否纳入后续迭代。

## 期望 vs 实际
- 期望：PRD 有本功能定义 + 可落地枚举与验收，前端/image-prompt/QA 据此推进。
- 实际：PRD 无此功能，下拉枚举/限额/验收待定。

## 处理记录
- 2026-06-04 [开发] 创建并派给 PM；细节见 spec §1/§4.3/§8。状态=已确认，owner=PM
