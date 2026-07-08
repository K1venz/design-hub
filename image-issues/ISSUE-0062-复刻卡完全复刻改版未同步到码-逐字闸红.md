---
id: ISSUE-0062
title: 复刻卡「完全复刻」改版未同步到代码——卡↔码逐字闸红、阻迁移轮绿门
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 阻 migration 轮全绿门（prod 功能不受影响，见下）
reporter: 开发
owner: coordinator    # 需定夺：实现改版(自成 issue+签字) vs 撤/缓卡以对齐
created: 2026-07-08
updated: 2026-07-08
related:
  - prompt: image-prompt/clone-mode-cards/复刻.md（d0b9d66 2026-06-22 改版）
  - spec: docs/superpowers/specs/2026-06-15-clone-full-replicate-redesign-design.md
  - code: image-code/src/design_hub/application/listing/prompt_composer.py（_CLONE_FULL / CLONE_MODES）
  - test: image-code/tests/test_prompt_cards.py::test_clone_blocks_match_card
---

## 现象
复刻模式卡在 **2026-06-22（commit d0b9d66）** 被改版：「高度复刻」→「完全复刻」，
重写档 2 文本 + 新增「完全复刻·有字模板」块（overlay 双块、{overlay_texts} 注入槽）。
**代码侧从未同步**：`CloneModeRegistry` 仍是旧版——
`_CLONE_FULL = "复刻·高度复刻：…版式参考图…照搬其视觉结构…"`、
`CLONE_MODES = ("参考风格", "高度复刻")`。
卡↔码逐字闸 `test_clone_blocks_match_card`（`_CLONE_FULL == blocks[1]`）因此**红**，
致本地全量 pytest 红（141 绿 + 1 红）。参考风格块未变、断言仍绿。

## 复现步骤
1. `cd image-code && uv run pytest tests/test_prompt_cards.py::test_clone_blocks_match_card`
2. 观察 diff：代码「复刻·高度复刻」 vs 卡「复刻·完全复刻·无字版」。

## 期望 vs 实际
- 期望：卡=码单一事实源，逐字闸绿、全量 pytest 绿（迁移轮 CI 门可过）。
- 实际：卡领先码约两周，闸红，全量 pytest 红。**注意：prod 无影响**——线上复刻走
  「高度复刻」运行正常，此为卡↔码一致性 / 绿门缺陷，非线上功能 bug。

## 影响面（为何不能 dev 静默改）
改版是有设计稿的正式重构，最小「照抄卡文本」并不够，牵扯多方：
1. **枚举 + 界面标签重命名** 高度复刻→完全复刻：`clone_mode` 落库为字符串，
   **prod listing_job 存量行 clone_mode="高度复刻"** ——重命名影响存量行读取/配方回显，
   属数据口径变更，需**用户签字**（DB 铁律）+ 兼容策略（映射旧值 or 数据回填）。
2. **CloneRequest 新增 overlay_texts**（仅「完全复刻」可带；「参考风格」带 overlay→400）
   + 无字/有字**双块按 overlay 选块**逻辑（同卖点图 ImageTypeRegistry）+ quality=high。
3. **前端** UI 标签「高度复刻→完全复刻」+ overlay 输入投影。
4. QA 视觉复验（字样复刻、竞品文字泄漏命门）。
即：这是一个独立特性（≈ ISSUE 级），非 category 那种一列小改，需 coordinator/PM 排期 + 用户签字。

## 待定夺（coordinator）
- **A**：实现「完全复刻」改版——另开 issue，dev(码)+prompt(卡已就位)+frontend(标签)+QA，
  含 clone_mode 重命名的存量数据策略（用户签字）。迁移轮/绿门在此完成后恢复。
- **B**：暂缓改版、撤回/回滚卡到「高度复刻」以对齐现码，逐字闸即绿；改版排入 backlog。
- 在 A/B 落定前，迁移轮全绿门被此红卡阻（category 的 d1a2b3c4e5f6 + 0057 的
  c9e4a1b73d52 本身 up/down 干净、与本红无关，但同一 pytest 门会被拖红）。

## 处理记录
- 2026-07-08 [开发] 实现 listing_job.category 时全量 pytest 发现本红；核实非 category 引入
  （工作树未碰 prompt_composer/test_prompt_cards），确认卡 d0b9d66 改版未同步到码。
  状态=已确认，owner=coordinator 定夺 A/B。
