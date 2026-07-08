---
id: ISSUE-0052
title: 套图白底图被用户 styling/场景 prompt 污染——「纯白无背景」压不过强场景描述
status: 已关闭        # 档A组装侧上线+prod真图抽验双向PASS(强场景下白底纯白+文字保真、场景图未误伤)
severity: P2          # 高 P2：白底图=平台主图合规向核心图型，80% 命中率、影响旗舰套图质量；但非资损/非阻断（图仍出、只是背景错）
reporter: 开发        # /showcase 子 agent 生成 5 套精选时发现（coordinator #933④ 转述）
owner: —              # 已关闭：档A剥离生效、双向PASS；prompt卡措辞强化=可选后续backlog(不阻)
created: 2026-07-02
updated: 2026-07-07
related:
  - PRD: §3.12.14 套图（白底图型语义：纯白底主图/平台主图合规向）
  - 卡体系: 图型卡（白底/场景/卖点）× 用户文本组装序（保真块 × 图型卡 × 用户文本 × modifier）
  - 决策: listing「路A」= 产品 styling 走用户 prompt 兜底（project_listing_launch_gates）——本 bug = 路A × 白底图型 的冲突面
  - 群聊: image-gen#1 #933④（/showcase 子 agent 实测发现，coordinator 建议 P2 prompt+dev 会诊）
---

## 现象（/showcase 子 agent 批量实测，#933④）
生成 5 套精选套图时，**白底图型 5 套中 4 套被污染**：白底图型卡的「纯白无背景」指令**压不过用户 styling prompt 里的强场景描述**（如「放在木桌上/厨房/暖光场景」），导致本应纯白底的主图出成了带场景的图。

## 根因初判（待 prompt/dev 会诊坐实）
组装序 = 保真块 × 图型卡 × **用户文本** × modifier。白底图型卡写「纯白底/无背景」，但用户自由文本（场景描述）与之**并存注入**；图像模型倾向遵循更具体的场景描述 → 白底图型的「纯白」被场景文本盖过。
本质 = **listing「路A」（用户 prompt 兜底 styling）× 白底图型** 的冲突：用户的场景/styling 文本对**场景图/卖点图**是对的，但对**白底图**是污染源——白底图本就该无场景。

## 修复方向（子 agent 建议 + PM 框定）
- **组装侧**：白底图型组装时**剥离/削弱用户场景文本**（dev：按 image_type=白底 时，用户自由文本不注入或降权）。
- **卡侧**：白底图型卡「纯白无背景」措辞强化 / 增负向约束（prompt：卡权威，逐字核对闸同步）。

## ✅ 产品口径拍板 = 档 A（PM 2026-07-02，dev 组装侧可行性确认 #939、coordinator #938 同倾向）
**白底图型对用户文本的处置粒度**——两档：
- **✅ 档 A（拍定）**：白底图型**完全剥离用户自由文本**（用户 styling 只作用于场景图/卖点图；白底=纯白主图合规向、不吃场景），最干净、根治污染。
- 档 B（否）：只剥离/降权「场景类」文本、保留「产品强调类」文本——需判别文本类别、复杂度高、易漏，否。
**拍板理由**：白底图语义本就排斥场景、YAGNI 不做文本分类；**dev #939 确认组装侧可行**（白底图型 compose 剥离 user prompt、保 modifiers + 白底块）。**卡侧措辞强化归 prompt 权威**（在线时复核/细化，不阻本口径）。落地=组装侧按 image_type=白底 剥离用户自由文本（dev）+ 白底卡措辞强化（prompt，可选增强）。

## 验收标准（QA，修后）
1. 白底图型：带强场景 styling prompt 的套图请求，**白底图仍出纯白底**（无场景污染）；场景图/卖点图仍正常吃用户 styling。
2. 多产品 × 强场景文本回归（沿套图保真×图型矩阵），白底图零场景泄漏。
3. 卡↔code 逐字核对闸绿（若改白底卡措辞）。

## 处理记录
- 2026-07-02 [PM] coordinator #933④ 转 /showcase 子 agent 实测发现，PM 分诊开条：定级 **P2**（白底=核心主图图型、80% 命中，但非资损/非阻断）。
  根因初判=路A 用户文本 × 白底图型冲突。修复方向组装侧剥离+卡侧强化。**PM 待定产品口径（档 A 完全剥离 vs 档 B 只剥场景），倾向 A**。
  owner=prompt（卡权威主）+ dev（组装侧）会诊。**排期注**：coordinator #928 排在 /showcase 部署 + 0050/0051 之后，避免同期改 image-code/image-prompt 撞车；prompt 卡侧可先行准备。
- 2026-07-02 [PM] **产品口径拍板 = 档 A**（白底图型完全剥离用户自由文本）：dev #939 确认组装侧可行（compose 剥离 user prompt、保 modifiers+白底块）、coordinator #938 同倾向 A。落地=组装侧剥离（dev）+ 白底卡措辞强化（prompt 权威在线复核，可选增强、不阻口径）。排期照旧（0051 后）。owner=prompt+dev。验收=带强场景 styling 的套图白底图仍纯白、场景/卖点图不受损。
- 2026-07-07 [dev] **档 A 组装侧完成**（commit `8eeb6b8`，纯组装侧、校验语义不变；coordinator #988 派工「chat P3-#5 后接 0052」）：
  ① `ImageTypeRegistry.drops_user_styling(image_type)`=图型语义单一事实源（白底→True），`WHITE_BG_TYPE` 常量消散落魔法串；
  ② `compose_prompt(drop_user_text)`：白底走剥离分支=仅 **保真块 + 白底卡块 + modifiers**、**不注入用户自由文本**；场景/卖点保留；
  ③ `build_listing_prompts` 按 image_type 传 `drop_user_text=type_registry.drops_user_styling(...)`。
  **用户文本仍必填**（供场景/卖点），仅白底图不注入 → **无校验语义改动**（纯组装侧）。
  自测（mock 验组装产物，强场景 styling=「高山竹匾晾晒花生的自然场景，远处青山蓝天」）：白底**不含**用户场景文本、保 保真块+
  白底卡块（"纯白无缝影棚背景"）+modifiers；场景/卖点用户文本**不受损**（含）。ruff+mypy(src) 绿、pytest 100 绿+1 已知 WIP 红。
  **卡措辞强化**（prompt 权威、可选增强不阻口径）待 prompt 窗口回来补；**真图抽验**（带强场景套图白底仍纯白）交 QA（≤¥2）。
  status 已确认→待验证；owner 提示词→coordinator（编排本波次 QA 真图抽验；prompt 卡措辞为可选后续）。
- 2026-07-07 [PM] **组装代码随 0054 波上线 prod、但待验证保持**（coordinator #1002 提前 key 前部署）：
  8eeb6b8 白底剥离组装代码随 0054 波上线 prod（bundle/回滚镜像同 0054）；**但组装代码上线 ≠ 关账**——
  **关账 gate = key 恢复后 ¥2 真图抽验**（带强场景 styling 的套图，验白底纯白 + 场景/卖点不误伤），coordinator 直接在 prod 跑（省 qa 一轮）。
  当前 P0 事故（ISSUE-0056 apinebula 平台侧）致出图断 → 真图抽验**阻塞在 key 恢复**。status 维持**待验证**、owner=coordinator。
  key 恢复 → coordinator prod ¥2 抽验绿 → PM 关账 0052。**卡措辞强化**仍待 prompt 窗口（可选、不阻本口径）。
- 2026-07-08 [coordinator+PM] **✅ prod 真图抽验双向 PASS、关账（#1094）**：出图恢复后 coordinator prod 真图抽验（强场景 styling=**海边沙滩椰树**）——
  ① **白底图纯白如洗 + 文字全保真**（档 A 剥离用户自由文本生效、白底不吃场景）；② **场景图海滩氛围拉满**（用户文本**未误伤**、场景/卖点正常吃 styling）。**双向 PASS**（该剥的剥、该留的留），评图证据 coordinator 人工核、图存 /tmp/0052-*.png 归档 image-qa。**PM 关账**：档 A 组装侧（`8eeb6b8`）prod 真图坐实 → status→**已关闭**。**卡措辞强化**=可选后续 backlog（不阻、本口径已达成）。
