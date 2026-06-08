---
id: ISSUE-0038
title: listing 上线前文案质控 — 治 AI 直出偶发 typo（prompt 文案约束 + 人工校对）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 上线前 gate 之一；非阻断验收（base 已定档），可修
reporter: PM
owner: image-prompt   # prompt 加文案约束为主；人工校对环节 = 上线运营 SOP
created: 2026-06-08
updated: 2026-06-08
related:
  - PRD: §3.12.10 上线前清单 gate 3
  - issue: ISSUE-0035（验收发现）、ISSUE-0022（image-prompt 话术片段）
---

## 背景
listing 验收（ISSUE-0035）共评 8 张花生样张，PM 逐字核文案：**7/8 全对**，唯 1 处 typo：
样张8「亚马逊-16x9-英文」大标题 `PRENIUM` → 应 `PREMIUM`（另：亚马逊1x1 徽章 "MADE REAL PEANUTS" 漏 "WITH"，角标装饰、轻微）。

**定性**：AI 直出图内文字的 typo 是**通病、非 base 特有**（vip 同底模也偶发，gpt-image 系列在图内渲染文字本就不稳）→ 不影响 base vs vip 档位（base 已定档），但上线前需治理，避免投产物料带错字。

## 需 image-prompt / 运营产出
1. **prompt 文案约束（image-prompt 为主）**：在 listing prompt 组装（`prompt_composer` / 话术片段 ISSUE-0022）里加约束，降低图内文字出错率：
   - 明确"广告文字必须拼写正确、语言匹配平台（英文平台→英文、中文平台→中文）、无臆造词"；
   - 关键词（PREMIUM/品牌名等）尽量短词、避免易错长词；必要时减少图内强制文字量。
2. **人工校对 SOP（运营/上线流程）**：listing 出图后**人工扫一遍图内文字**（拼写/语言/排版），翻车的那张**重生成或调 prompt** 后再交付。这是 AI 直出物料的必要质控环节，写入上线运营 SOP。
3. （可选增强）后处理：探索"出图后 OCR 校文案"自动化，命中可疑词触发重生成——本期不做，记 backlog。

## 期望 vs 实际
- 期望：listing 投产物料图内文字零错字、语言/排版正确。
- 实际：AI 直出偶发 typo（验收样本 1/8），无质控环节则可能带错字上线。

## 处理记录
- 2026-06-08 [PM] listing 验收（ISSUE-0035）+ 用户拍板 base 定档后，PM 逐字核文案发现样张8 PRENIUM typo（AI 直出通病、非 base 特有）。开本条作上线前 gate 之一（PRD §3.12.10 gate 3），owner=image-prompt（prompt 约束）+ 运营（人工校对 SOP）。非阻断 base 定档，上线前治理。
