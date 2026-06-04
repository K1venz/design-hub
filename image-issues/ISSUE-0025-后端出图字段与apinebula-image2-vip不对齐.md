---
id: ISSUE-0025
title: 后端出图字段与 apinebula image2-vip 对比（实测推翻 size/image[]，残留多图edit+quality）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 原判 P1 三致命经 QA 实测推翻 2 个；残留多图 image[] 验证 + quality 省钱
reporter: PM          # 受命对 /generate 做可用性判断时发现
owner: 开发           # 残留①多图 image[] QA 已受控实测(上游接受/未失败,见记录)；残留②quality 省钱归开发
created: 2026-06-04
updated: 2026-06-04
related:
  - doc: https://docs.apinebula.com/docs/advanced/image/image2-vip （上游真实规格，2026-06-04 Playwright 抓取逐字核对）
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py（_edit 用 image[]；_generate/_edit 传 n；size 直拼；未传 quality）
  - code: image-code/src/design_hub/application/listing/sizing.py（比例映射产出 1024 系列，上游不支持）
  - code: image-code/src/design_hub/application/routing/table.py（DEFAULT_CANDIDATES=6 / MAX_CANDIDATES=12 → n>1）
  - config: image-code/.env（GPT_IMAGE_BASE_URL=https://apinebula.com/v1 ; GPT_IMAGE_MODEL=gpt-image-2-vip）
  - spec: docs/superpowers/specs/2026-06-04-listing-image-generation-design.md §6.1（n>1 风险已预判，本条以官方文档坐实）
  - issue: ISSUE-0007（edit 超时回落）、ISSUE-0021（listing PRD，比例映射需同步改 2048 系列）
---

## 现象
PM 受命对 `/generate` 做可用性判断：抓取上游 apinebula **image2-vip** 文档逐字，与后端实际构造的请求对比。
后端 `.env` 实配 `model=gpt-image-2-vip` + `base_url=https://apinebula.com/v1`——**即面向本文档这个分组**，
故下述不匹配为真实问题，非选型假设。结论：**3 处致命字段不对齐 + 2 处风险，`/generate` 默认参数对 image2-vip 不可用，listing 链路（1024 size）必挂。**

## 对比表（后端实际发 vs image2-vip 文档要求）
| 维度 | 后端实际发出 | image2-vip 文档要求 | 判定 |
|---|---|---|---|
| endpoint 文生图 | `{base}/images/generations`(JSON) | `POST /v1/images/generations`(JSON) | ✅ |
| endpoint 图生图 | `{base}/images/edits`(multipart) | `POST /v1/images/edits`(multipart) | ✅ |
| model | `gpt-image-2-vip`(.env) | `gpt-image-2-vip` / `gpt-image-2-pro` | ✅ |
| 鉴权 | `Authorization: Bearer` | `Authorization: Bearer` | ✅ |
| 响应解析 | `data[].url` → 否则 `data[].b64_json` | `data[0].url` / `data[0].b64_json` | ✅ |
| **size** | `1024x1024 / 1024x1536 / 1536x1024`（listing sizing.py；海报流取请求 w/h） | **仅 `2048x2048 / 3840x2160 / 2160x3840`**（最长边≤3840，4096 不支持） | ❌ 致命 |
| **n** | 海报默认 6（MAX 12）、listing 1/3/5/7 | **仅支持 1** | ❌ 致命 |
| **edits 图字段名** | `image[]`（同名重复） | **`image`（同名重复，无 `[]`）** | ❌ 致命/高危 |
| quality | 不传 | `low / medium / high / auto` | ⚠️ 风险 |
| 单价(预扣) | composition 1.19 / 兜底 0.10 | 文档未给 vip 价 | ⚠️ 风险 |

## 三处致命
1. **size 全不匹配**：`sizing.py` 硬编码 1024 系列；上游只认 2048 系列。1024 请求大概率 400/不符 → listing 出不了图。
2. **n 只支持 1**：`openai_compat._generate/_edit` 直接把 `n`(>1) 发上游；海报默认 6。spec §6.1 已预判"退化为并发 N 次单图"，**现官方文档坐实必须做**。
3. **edits 多图字段名**：`openai_compat._edit` 用 `("image[]", ...)`（OpenAI gpt-image-1 协议），但 image2-vip 文档明确多图是重复 `image`（`-F "image=@a" -F "image=@b"`）。`image[]` 可能被上游当未知字段忽略 → 参考图丢失、图生图退化为文生图/失败。

## 两处风险
4. **quality 未传** → 走上游默认档，成本不可控（low~high 价差大）。建议显式传 + 入 ModelConfig 可调。
5. **vip 实扣单价未核** → CostGuard 预扣/对账可能失真。需核 vip 分组实价更新 unit_cost。

## 一个需开发核实的矛盾
ISSUE-0007 记「文生图实测正常出图」。若 size=1024 真被 vip 硬拒，文生图不应成功。实测当时可能：
(a) 用了 2048 系列 size；(b) n=1（控成本，见 memory）；(c) 上游对越界 size 做了容错。
→ **请开发核实 ISSUE-0007 实测时实际发出的 size/n**，确认上游对 1024/n>1 是硬 400 还是容错。这决定改造紧迫度与是否已有线上误判。

## 期望 vs 实际
- 期望：后端请求字段与 image2-vip 对齐，默认参数即可真实出图。
- 实际：size/n/图字段名三处不符；`/generate` 默认 n=6 对 vip 不可用；listing 1024 size 必挂。

## 修复方向（供开发，遵循"老代码适配新规格、不加兼容层"）
- **size**：`sizing.py` 比例映射目标改 2048 系列（建议 1:1→`2048x2048`；竖版 3:4/9:16→`2160x3840`；横版 16:9→`3840x2160`）。前端比例下拉值（ISSUE-0021）不变，只改后端映射的目标尺寸。海报流 size 来源同步约束到上游三尺寸（非法 size fail-fast）。
- **n**：`openai_compat` 对 n>1 退化为**并发 N 次单图**（generations/edits 各发 n=1，每张单算 seed/成本），或在 service 层循环；API 契约不变。
- **edits 字段名**：`image[]` → 重复 `image`。
- **quality**：显式传（建议 medium 起步），入 ModelConfig。
- **单价**：核 vip 实扣价，更新 `unit_cost` / ModelConfig。

## 连带影响（PM/QA）
- **ISSUE-0021**：listing PRD 的比例→尺寸映射 PM 会同步改成 2048 系列（之前误写 1024，已更正）。
- **QA**：listing/海报真实出图验收的 size/n 口径按上游（n 实际由并发实现，单张计费）。

## 处理记录
- 2026-06-04 [PM] 抓取 apinebula image2-vip 文档（Playwright 渲染逐字）对比 `openai_compat.py` / `sizing.py` / `routing/table.py` 实际请求，确认 3 致命 + 2 风险；后端 .env 实配 vip 分组，不匹配为真问题。开条目派开发，owner=开发，severity P1，status=已确认。
- 2026-06-04 [PM] 用户拍板修复口径（强化修复方向，owner 仍=开发）：
  **① `n` 对上游固定为 1**——前端张数下拉 1/3/5/7 = 候选数，后端选 N 张即发 N 次单图请求（每次 n=1，独立 seed/计费），不再期望上游一次返回多张；
  **② 比例映射定为上游真实 2048 系列**：1:1→2048×2048、3:4/9:16→2160×3840、16:9→3840×2160（已写入 PRD §3.12.3，开发据此改 `sizing.py`）；
  **③ `image[]`→`image`、显式传 `quality`、核 vip 实价** 维持原修复方向。
  PRD §3.12 已据此定稿，开发可开工。
- 2026-06-04 [PM] ⚠️ **重大更正（翻 QA 用例14 实测后，自我纠错）**——本条原判 size/image[] 为"致命"是**仅凭上游文档的误判**，被真实 e2e 推翻：
  ISSUE-0023 用例14（2026-06-04 真花钱）：`.env=gpt-image-2-vip+apinebula`，单图 + ratio=3:4 → **真实出图 `1024×1536` 成功、质量正常、¥1.19/张**（脚本 image-qa/listing_real_e2e.py）。
  逐条修正：
  · **size 非问题**：1024 系列实测可用，文档"仅 2048"不准 → **撤回"改 sizing.py 为 2048"**（上一条 ② 作废）。PRD §3.12.3 已改回 1024 系列。
  · **edits 字段名 image[] 非致命**：单图 `image[]` 上游已接受并出图；**仅多图 image[]≥2 仍待验证**（用例14 残留，QA 标"仍待覆盖"）。
  · **n**：用户已定上游恒 1 + 后端 N 次单图，不依赖上游一次返回多张（上一条 ① 仍有效）。
  · **真正残留**：① 多图 `image[]`≥2 真实 edit 上游是否支持（owner→QA 受控跑；不支持则后端退化为并发逐图，契约不变）；
    ② quality 未传 → 走 high 档（实测 ¥1.19/张偏贵），显式传 `medium` 可显著降本（owner→开发，省钱优化，非阻断）。
  · vip 实价已知：high 档 ¥1.19/张。severity P1→P2，owner→QA（多图实测优先）。
  · **教训**：上一轮仅据文档下"致命"结论并改了 PRD/sizing 方向，未先核 QA 已有实测——**实测优先于文档**，下次先翻 image-qa 再下判断。
- 2026-06-04 [QA] **残留① 多图 image[]≥2 受控实测（真服务器 :8002 真 gpt-image，n=1，¥1.19）**：
  传 2 张不同花生图(两步流 upload → upload_ids[2]) → `provider._edit` 以 `image[]` 重复字段发上游 →
  **apinebula 接受、出图成功（HTTP 200，gpt-image-2，1024×1024，312s）、未失败/未退化报错** →
  **推翻文档推测「image[] 被忽略→出图失败」**；故后端**无需退化为并发逐图**（spec §6.1 兜底暂不必要）。
  脚本 image-qa/listing_real_e2e.py（D），报告 §8.2。
  ⚠️ **存疑（黑盒局限）**：2 张输入均花生包装、外观相近，无法 100% 确认第 2 张真被合成使用（312s>单图 116s 为旁证）。
  如需确证「多图真融合」，建议用 2 张**视觉差异大**的输入做 A/B 受控复跑（再花 1 张）。
  残留① 功能层面已通（不阻断）；残留②（显式传 quality=medium 省钱）仍归开发。owner→开发（残留②）。
