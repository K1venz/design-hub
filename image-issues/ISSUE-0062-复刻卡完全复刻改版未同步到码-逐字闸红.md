---
id: ISSUE-0062
title: 复刻卡「完全复刻」改版=用户 HOLD 哨兵（逐字闸红=既有已知 WIP 标记，非新 bug）
status: 挂起          # C=维持 HOLD（用户 2026-06-22 点名挂起等自测，红测=改版收尾前哨兵，基线一直记+1 known WIP red）
severity: P3          # 已知 WIP 哨兵·prod 无影响·迁移轮 gates around 照跑；非线上 bug、非绿门真阻断
reporter: 开发
owner: 用户            # 用户挂起的决策——等他自测「完全复刻」改版后拍（A 实现 / 撤 HOLD）；A/B 现都不动
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

## ✅ 处置 = C 维持 HOLD（coordinator #1086 澄清 · 非新 bug）
**本条不是新发现的卡↔码 drift，而是「完全复刻改版」的既有 HOLD 哨兵**：**用户 2026-06-22（卡改 d0b9d66 后）点名 HOLD、等他自测**——码故意未同步、`test_clone_blocks_match_card` 红=改版收尾前的**哨兵**，团队所有 QA 基线一直记「**+1 known WIP red**」。故：
- **A（实现改版·含 clone_mode 重命名存量行→用户签字）/ B（回滚卡对齐现码）都不动**——**那是用户挂起的决策**，等他自测「完全复刻」后拍（要么收尾实现=撤 HOLD，要么弃改版）。
- **迁移轮不受影响照跑**：category `d1a2b3c4e5f6` + 0057 `c9e4a1b73d52` 本身 up/down 干净、与本红无关；qa 先行**gates around 这条已知 WIP red**（基线容忍口径照旧）、非真阻断。
- **prod 无影响**：线上复刻走「高度复刻」运行正常。
- （历史框的 A/B 定夺为 dev 开条时缺 HOLD 上下文所写，已由 C 取代——见下处理记录。）

## 处理记录
- 2026-07-08 [开发] 实现 listing_job.category 时全量 pytest 发现本红；核实非 category 引入
  （工作树未碰 prompt_composer/test_prompt_cards），确认卡 d0b9d66 改版未同步到码。
  状态=已确认，owner=coordinator 定夺 A/B。（**注：dev 此时缺 HOLD 上下文=compaction 后未带上，误当 P1 blocker 上报；见下 C 澄清。**）
- 2026-07-08 [coordinator+PM] **C 维持 HOLD·合并既有上下文（coordinator #1086 澄清、dev-1 #1087 认、PM 并入）**：本红=**「完全复刻改版」用户 HOLD 哨兵**（用户 2026-06-22 卡改 d0b9d66 后点名挂起等自测），非新 bug；基线一直记「+1 known WIP red」、迁移轮 gates around 照跑、prod 无影响。
  **处置=C：A/B 都不动**（用户挂起的决策、等他自测拍）。frontmatter 改 **挂起 / severity P3 / owner=用户**。**本条即「+1 known WIP red」的权威登记**——防后人再「发现」一次当新 bug 报（memory `project_clone_full_replicate_hold` 同步）。PRD §3.13 🔄块「实现 in-flight」→「HOLD 待用户自测」纠正。**用户自测完拍改版方向时**，PM 再据其决策开实现 issue（A：clone_mode 重命名存量行需用户签字）或正式弃改版。owner=用户（HOLD 决策）。
