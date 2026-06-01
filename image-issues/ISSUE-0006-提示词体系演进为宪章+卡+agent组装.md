---
id: ISSUE-0006
title: 提示词体系演进为「宪章+卡+agent 组装」并修正现状 7 个反模式
status: 待复现        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 影响真实感/品牌保真/USP,质量命脉
reporter: 提示词工程   # 新增角色
owner: 开发           # 球交给 Dev:评估 + 实现
created: 2026-06-01
updated: 2026-06-01
related:
  - PRD: §3.4 Prompt 编排子系统 / §3.4.10(本属 V2"AI 生成 Prompt")
  - code: image-code/src/design_hub/application/prompt/orchestrator.py
  - code: image-code/src/design_hub/application/prompt/libraries/quality.py
  - code: image-code/src/design_hub/application/prompt/profiles/categories/food.py
  - code: image-code/src/design_hub/application/prompt/families/family5.py
  - spec: image-prompt/00-charter.md
  - spec: image-prompt/examples/花生-端到端.md
---

## 现象
现状 `PromptOrchestrator` 是确定性字符串拼接,对"真实感/品牌保真/不过分修改"有系统性缺陷。
以 FOOD+FRESH+族5+EDIT 实测重建的输出(详见 `image-prompt/examples/花生-端到端.md` 对照节),暴露 7 个反模式。

## 期望 vs 实际(7 个反模式)
| # | 现状(实际) | 期望(改后) | 涉及文件 |
|---|---|---|---|
| 1 | `QualityLibrary` 给 GPT 追加 `8K超高清/电影级画质/商业广告质感` | 删除这类催生 AI 假感的词,换"真实质地+自然光+瑕疵" | libraries/quality.py |
| 2 | family5 收尾 `要求高级质感、非AI廉价感` | 删除许愿式空话,改可执行摄影语言 | families/family5.py |
| 3 | FOOD 无紫花生/USP 本色锁定 | 品类命门正向防御(食品:保留产品本色与质地特征) | profiles/categories/food.py |
| 4 | `typography_block` 文字无引号无 verbatim,且把元指令`(内容+位置+字号…)`并入文案 | 引号锁原文 + verbatim + 只锁关键字;元指令不得进 prompt 正文 | rules.py: typography_block |
| 5 | family5 `产品宣传海报/电商广告` 海报腔 | 改"真实摆拍照"定调 | families/family5.py |
| 6 | 负面走否定句(provider `（请避免：…）`) | gpt-image 无 negative 字段、对否定弱 → 全部正向化 | profiles + libraries/negative.py + providers/openai_compat.py |
| 7 | 无摄影语言/瑕疵/真实光描述 | 强制注入摄影语言 + 真实质地瑕疵线索 | orchestrator + profiles |

## 建议的架构演进(与 image-prompt 体系对齐)
将 orchestrator 从"死拼接"演进为"**宪章 + 品类卡 + 风格卡 + agent 组装**":
- 宪章/卡的内容 spec 见 `image-prompt/00-charter.md`、`category-cards/`、`style-cards/`。
- agent 组装为 V2 目标;**V1 可先落"现状 7 反模式修正",不引入 agent 也能立刻提质**。
- 二者解耦:先做 7 修正(快、低风险),再评估 agent 化。

## 需 Dev / Ops 确认的依赖
- **[Ops]** 中转站网关返回的 `model` 究竟是 `gpt-image-2` 还是 `gpt-image-1.5`?
  - 若为 1.5 → edits 可加 `input_fidelity=high`(2.0 已禁用该参数),品牌保真直接上一台阶。依据:`image-prompt/references/gpt-image-2-能力边界.md` §4。

## 环境 / 上下文
gpt-image-2.0,`/images/edits`(主)+`/images/generations`;现状 EDIT 只传 1 张参考图、无 mask。

## 处理记录
- 2026-06-01 [提示词工程] 创建,状态=待复现;附宪章/品类卡/端到端示例与 7 反模式清单,owner=开发。
