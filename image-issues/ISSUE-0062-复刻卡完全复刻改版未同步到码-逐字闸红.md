---
id: ISSUE-0062
title: 复刻卡「高度复刻→完全复刻」改版——用户拍板上改版（版式整张迁移）·实现波
status: 修复中        # HOLD 解除:用户看A3/B3判决图拍板上改版(#1148)→实现波开工(卡物化+存量行迁移[签字]+overlay双块+前端标签+知识库引导)
severity: P2          # 功能改版(复刻语义升级=版式整张迁移)+涉存量行数据迁移(须用户签字)；非资损、内测灰度
reporter: 开发
owner: 开发+frontend-b # 实现:dev(卡物化+data migration+枚举/openapi+overlay双块)+frontend-b(模式标签/tooltip/codegen)；数据迁移待用户签字
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
- 2026-07-13 [coordinator+PM] **🔓 HOLD 开封中：用户「先给我看看效果，再决定」→ dev 跑 A/B 实拍对比演示单（coordinator #1136）**：20 天 HOLD 进入决策流程。
  **dev 演示单**（**隔离 worktree、main 零污染、用完清理**）：① worktree 内临时物化改版卡（d0b9d66「完全复刻」措辞）进 CloneModeRegistry（只在 worktree 让红测变绿）；② 本地真图后端同一组输入跑两次 clone——**A=现网「高度复刻」 vs B=改版「完全复刻」**（输入=showcase 强版式卖点图当爆款参考 + image-qa/品类扩展素材 跨品类产品图，各出 1 张 A/B 共 2 张≈¥0.8、可各 2=¥1.6 封顶）；③ 产物=图存本地报 coordinator + 两卡措辞 diff 要点（改版改了什么行为）。**coordinator 拿图给用户拍板**。
  **用户拍板两分支（PM 待据决策接棒）**：**上改版**=洗掉 HOLD → PM 开实现 issue（clone_mode「高度复刻→完全复刻」重命名牵动 prod 存量行=**数据口径变更须用户签字** + CloneRequest.overlay_texts + 双块选块 + 前端标签 + QA 视觉复验）；**弃改版**=回滚卡对齐现码、逐字闸转正常绿、正式弃。owner=开发（跑演示）→用户（拍板）→PM（据决策接棒）。status 保持挂起（决策流程中、改版码仍未落 main）。
- 2026-07-13 [dev] **A/B 判决图三轮出稿**（worktree、main 零污染、¥2.4 内）：判决轮 A3/B3（参考=版式主导图·5 罐紫底俯拍 flat-lay·产品=花生袋）**决定性**——**A3 高度复刻=丢版式自起一张常规产品场景**（没紫底/没俯拍/没借版式），**B3 完全复刻=整张版式结构迁移**（紫底+俯视 flat-lay 机位照搬、产品换花生袋居中）。佐证轮 A2/B2 示「高度借风格道具自适应 vs 完全连道具位照搬」。带歪 exhibit（强产品参考→两档都复刻成参考图产品）=真实风险：参考图须「场景/版式主导、产品占比弱」。compare.html + 图 /private/tmp/claude-502/0062-demo/。
- 2026-07-13 [coordinator+PM] **🏁 用户拍板=上「完全复刻」改版（#1148）→ 0062 转实现波、HOLD 解除**：判决轮 A3/B3 定案（完全档版式整张迁移=价值坐实、第二档不回炉）→ 用户拍板 B。**status 挂起→修复中**、20 天 known WIP red 待归零。**本波首跑完整 CI 工作流**（用户指令：push 远程 dev → gh 开 PR dev→main → CI ruff+pytest+gitleaks 绿 → 合并 → 从 main 部署 prod）。实现 scope + 验收定义见下两节。owner=开发+frontend-b（实现）+ 用户（数据迁移签字，coordinator 已递）。

## 实现 scope（用户拍板后，#1148）
- **① dev 卡正式物化落 main**：`CloneModeRegistry`「高度复刻」→「完全复刻」+ 措辞按 `d0b9d66` 设计稿，**逐字闸红转正常绿**（20 天 known WIP red 归零）。
- **② dev 存量行数据迁移（⚠️ 须用户签字，coordinator 已递）**：alembic **data migration**——`listing_job.clone_mode` 值 '高度复刻'→'完全复刻'，**纯 UPDATE、零 DDL、down 可逆**。**签字落地前不跑 prod 迁移；代码可先行**（sign gate 只卡 prod 数据订正那一步）。
- **③ dev clone_mode 枚举 / openapi 同步**。
- **④ CloneRequest.overlay_texts + 双块选块**（设计稿：完全复刻有字版 overlay 沿卖点图 2×12、参考风格档带 overlay→400）——**dev 评估随波 or 拆后续小波**（别为它拖 CI 首跑）。
- **⑤ frontend-b**：复刻工作台模式**标签/描述**「高度复刻→完全复刻」+ tooltip 新语义（"连构图道具位一并照搬"）+ codegen。
- **⑥ PM 知识库引导回写（DoD）**：判决轮两条教训入知识库使用引导——「复刻参考图选**场景/版式主导**（产品占比弱）、别拿别家**完整产品卖点图**当参考（会带歪成参考图的产品/竞品泄漏）；完全复刻会**连道具一并入画**」。

## 验收定义（QA，PM 定）
1. **完全复刻语义**：新 clone 单走完全档→出图**版式整张迁移**（构图/机位/道具位/配色照搬参考图、产品换用户的），非「借风格另起」。
2. **存量行迁移正确**：迁移后历史复刻单详情/配方显示**新名「完全复刻」**（旧值全订正无残留）；down 可逆验证。
3. **参考风格档零回归**（借保真块、不搬布局，不受影响）。
4. **overlay（⏭️ 拆后续小波、不在本波，PM 认可 #1151）**：完全复刻**有字版**（block[2] overlay verbatim 2×12、参考风格带 overlay→400 fail-fast）——**改版核心=版式复刻已交付**（逐字闸只核 block[0/1]、有字模板未物化不红闸），overlay 走下一轮小波、别拖本波 CI 首跑。
5. **前端**：模式标签/tooltip 新语义、codegen 对齐、复刻工作台零回归。
6. **知识库引导落地**：chat 问「复刻怎么用/参考图怎么选」答判决轮两条教训。
7. **卡↔code 逐字闸绿**（改版卡物化后 test_clone_blocks_match_card 转正常绿）。
8. **CI 门禁**：本波走 PR dev→main、ruff+pytest+gitleaks 全绿方合并。

## 处理记录（实现波）
- 2026-07-13 [dev+frontend-b] **前后端棒交付**：dev `daa3bd8`（改版卡物化 `_CLONE_FULL`=完全复刻·逐字==复刻卡 block[1]、**逐字闸转正常绿=20 天 HOLD 归零**、151 绿；存量行 data migration `e2f3a4b5c6d7` '高度复刻'→'完全复刻' 纯 UPDATE 零 DDL·down 可逆·**代码先行·签字前不跑 prod·PM 盯放行**；clone_mode 枚举 + **chat system_prompt 工具契约改「完全复刻」**否则 chat 吐旧值被拒；知识库引导落 config 逐字同步 PM draft）+ frontend-b `60bdbe3`（CLONE_MODES/desc 改「完全复刻」新语义、参考风格档零改、**存量行迁移后徽标自动显新名=验收②前端侧免费**、门禁 62 测绿）。**同波原子**（前端发新 key、后端须已认）。
- 2026-07-13 [PM] **两决策拍定**：① **验收④ overlay 有字版双块=拆后续小波**（认 dev #1151：改版核心=版式复刻已交付、逐字闸只核 block[0/1]，overlay 走下一轮、别拖本波 CI 首跑）；② **CI ruff 拦路（24 pre-existing 错全在老 migration 文件·非本次改动）→ 口径=`[tool.ruff] exclude=["migrations"]`**（PM 拍）：alembic 自动生成文件本不该 style-lint（import 排序/E501 长行对机器生成码无意义）、**mypy 已 `files=["src"]` 同 scope**，ruff 收敛到 src+tests=**修一致性非 shim**；不碰依赖版本、**gitleaks 秘密扫描不受影响**（安全扫描全量照旧）。dev 执行（pyproject.toml 属 image-code、PM 不写）。→ CI 首跑得以走通。
  **待**：dev exclude migrations 落 → 合并 QA → **push dev→PR dev→main→CI 全绿→合并→prod**（CI 首跑）；**存量行迁移待用户签字**（coordinator 已递、签字后 PM 确认放行 prod 数据订正）；知识库引导随改版波 dev 落 config。owner=开发+frontend-b（同波）→用户（签字）→PM（关账验收 8 条）。
- 2026-07-13 [dev+coordinator] **✅ CI 疏通 + prod 部署 gate 细化（#1152/#1154）**：dev `2a4748d` 落 `[tool.ruff] exclude=["migrations"]`（coordinator 独立同拍、多一条理由「老已应用迁移不回头动」）→ `uv run ruff check` **全净、151 绿、gitleaks 不受影响**；新迁移逻辑验过（只 '高度复刻'→'完全复刻'、参考风格/NULL 不动、down 可逆）。**0062 后端棒完整交付**（daa3bd8 物化+迁移+chat 契约+知识库 · 2a4748d CI 修）+ 前端 60bdbe3 同波原子就绪 → **可交 QA 合并轮**。
  **⚠️ prod 部署整体等签字（PM 盯死·gate 细化）**：`deploy.sh` **自带 `alembic upgrade`** 会自动跑 e2f3a4b5c6d7 → **整个 prod 部署卡用户签字**（非只迁移那一步）；**qa 侧迁移可先测**；**push dev / PR / CI 首跑 / 合并 main 都无 prod 效应、照跑不误**。→ **用户签了 @pm、PM 放行 prod 部署**（含数据订正）。follow-up overlay 有字版小波（验收④⏭️）dev 记着、这波稳后走。
