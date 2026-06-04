---
id: ISSUE-0022
title: image-prompt 产出 listing 下拉值→话术片段正式文案
status: 已确认
severity: P2
reporter: 开发
owner: image-prompt   # 球在 image-prompt：出话术片段文案
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md
  - issue: ISSUE-0021（PM 出下拉枚举，本条依赖其结果）
---

## 背景
listing 一键出图为「纯 prompt 直出」：最终 prompt = 用户自由文本 + **下拉值映射的话术片段**拼接，
直接喂 gpt-image-2 edit。这些话术片段是质量命脉，归 image-prompt 出正式文案。
后端会维护 `PromptModifierRegistry: (field, value) → 片段`，先放种子值占位，待本条替换。

## 需 image-prompt 产出
针对每个下拉的**每个取值**，给出注入 prompt 的中文话术片段。示例（种子值，待你优化/扩全）：
- `("platform","亚马逊") → "用于亚马逊电商平台的商品展示图"`
- `("region","美国") → "商品面向美国市场"`
- `("language","英文") → "广告文字使用英文"`

要求：
1. 覆盖 PM（ISSUE-0021）最终敲定的**所有下拉值**（平台/国家地区/语言；ratio 不走话术、由 size 承载）。
2. 片段为可直接拼接的短句，遵循 PRD §3.4 编写法则（场景化、避免歧义、必要时含否定约束）。
3. 语言下拉尤其重要：它决定**出图里广告文字的语种**，话术需明确"广告文字使用 X 语"。
4. 交付形式：一张 `(field, value) → 片段` 对照表（Markdown 即可），后端据此填 registry。

## 期望 vs 实际
- 期望：有正式话术对照表，替换后端种子值，保障出图质量。
- 实际：后端目前仅种子占位。

## 依赖
- 依赖 ISSUE-0021（PM 先定下拉完整枚举），否则取值范围不全。可先就已知值起草。

## 处理记录
- 2026-06-04 [开发] 创建并派给 image-prompt；机制见 spec §5。状态=已确认，owner=image-prompt
