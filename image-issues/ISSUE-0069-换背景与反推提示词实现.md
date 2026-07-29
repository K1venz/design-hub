---
id: ISSUE-0069
title: 换背景与反推提示词实现
status: 已确认
severity: P2
reporter: 调研
owner: 开发
created: 2026-07-29
updated: 2026-07-29
related:
  - research: image-market/2026-07-29-换背景与反推提示词实现规格.md
  - api-doc: https://docs.apinebula.ai/docs/advanced/image/gpt-image-2-1k/
  - code: image-code/src/design_hub/application/listing/requests.py
  - code: image-code/src/design_hub/application/chat/orchestrator.py
  - code: image-code/src/design_hub/config/chat_knowledge.md
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py
---

## 现象

现有项目已经具备二次编辑和 APINebula `/images/edits` 接入，但没有专用换背景用例、反推提示词能力和对应的 Chat 直接调用入口。现有 Chat 知识库还有比例、配方复用、额度口径和已删除界面文案等失真内容。

## 复现步骤

1. 从结果图进入二次编辑，可以通过自然语言尝试换背景，但没有文字/背景参考图双模式的专用工作流。
2. 在 Chat 上传图片并要求反推提示词，现有文字消息契约不会把真实图片内容交给 Chat 模型。
3. 对照 `chat_knowledge.md` 与当前代码，可发现 4:3 工作台入口、全任务一键复用、“扣积分”和“右上角内测免费”等表述不准确。

## 期望 vs 实际

- 期望：页面和 Chat 共用同一换背景能力；反推提示词复用已接入 Chat 模型；Chat 了解真实平台能力并优先直接完成任务。
- 实际：只有通用二次编辑；没有专用换背景、反推提示词和功能操作卡；知识库存在旧内容。

## 环境 / 上下文

- 用户已逐节确认完整设计。
- 第三方图片接口为 APINebula `gpt-image-2-1k`。
- 保留现有 `/listing/edit`，不重做二次编辑。
- 换背景支持文字描述和背景参考图，一次一张。
- 反推提示词使用已经接入的 Chat 模型，不新增模型。
- 实现必须复用现有任务、Worker、Provider、成本、SSE、存储和历史。
- 不做蒙版、画布、批量、2K/4K、RAG、背景库或新数据库表。

## 处理记录

- 2026-07-29 [调研] 完成接口、交互、Chat、知识库、错误处理和验收设计，用户确认，状态=已确认，owner=开发
