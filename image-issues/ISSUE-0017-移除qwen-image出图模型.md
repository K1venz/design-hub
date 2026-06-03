---
id: ISSUE-0017
title: 移除 qwen-image-pro 出图模型（用户定：多余，不接）
status: 待确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: 开发            # 改产品代码，QA 不动 image-code；F7 改投目标需开发/PM 拍板
created: 2026-06-03
updated: 2026-06-03
related:
  - code: image-code/src/design_hub/domain/enums.py:57（ModelName.QWEN_IMAGE_PRO）
  - code: image-code/src/design_hub/application/routing/table.py（F7 primary + fallback 链）
  - code: image-code/src/design_hub/composition.py（_MOCK_UNIT_COSTS + default_model_configs seed）
  - code: image-code/src/design_hub/application/prompt/libraries/quality.py（qwen 质量串）
  - 记忆: project_provider_scope_final（真实模型只接 gpt-image-2）
---

## 背景 / 需求
用户走查时明确：**不需要 qwen-image（千问出图），多余，去掉**。
qwen-image-pro 当前只是 Mock 占位（无真实 key），实测真实模型只剩 gpt-image-2。
> 注意区分：`ports/vision.py` 注释里的 **qwen-vl-max 是视觉理解辅助**（VisionAssist），不是出图模型，**不在本次移除范围**。

## 移除清单（image-code，开发执行）
1. `domain/enums.py`：删 `ModelName.QWEN_IMAGE_PRO = "qwen-image-pro"`。
2. `application/routing/table.py`：
   - `FAMILY_PRIMARY[TemplateFamily.F7]` 当前 = `QWEN_IMAGE_PRO` → **必须改投别的模型**（见下「需拍板」）。
   - `FALLBACKS[SEEDREAM_5] = (QWEN_IMAGE_PRO,)` → 改/删（seedream 的同档备选）。
   - 删 `FALLBACKS[QWEN_IMAGE_PRO] = (SEEDREAM_5,)` 整条。
3. `composition.py`：删 `_MOCK_UNIT_COSTS[QWEN_IMAGE_PRO]`；`default_model_configs()` 若含 qwen 一并移除（少 seed 一个模型）。
4. `application/prompt/libraries/quality.py`：删 `QWEN_IMAGE_PRO` 质量串条目。
5. `model_config` 表已 seed 的 `qwen-image-pro` 行：建议 seed 不再插 + 出一条清理（或置 `enabled=false`），避免仪表盘/admin 列表残留。
6. 全树搜 `qwen-image|QWEN_IMAGE_PRO` 确认无残留引用；ruff+mypy 绿。

## 需拍板（阻塞点）
**F7（family_7 中式节庆促销）原首选是 qwen，去掉后改投谁？**
- 选项 A（推荐）：F7 → `GPT_IMAGE_2`（唯一真实模型，保真；与"只接 gpt-image-2"的范围收窄一致）。
- 选项 B：F7 → `SEEDREAM_5`（仍 Mock 占位，等接真实再说）。
- 同理 `FALLBACKS[SEEDREAM_5]` 原备选 qwen，去掉后留空 `()` 还是改 `(GPT_IMAGE_2,)`，一并定。

## 期望 vs 实际
- 期望：模型集合只剩需要的（gpt-image-2 真实 + 其余必要 Mock），无 qwen-image。
- 实际：qwen-image-pro 仍在 enums/路由/seed/质量库中，F7 默认走它。

## 影响
- 不阻断现有出图（gpt/seedream 等不受影响）；属模型范围收窄 + 路由表清理。
- F7 改投目标定了即可一次性改完。

## 处理记录
- 2026-06-03 [QA] 用户定「去掉 qwen-image 出图」。QA 不改 image-code，开单指给开发，含牵连点与 F7 改投决策。状态=待确认，owner→开发。
