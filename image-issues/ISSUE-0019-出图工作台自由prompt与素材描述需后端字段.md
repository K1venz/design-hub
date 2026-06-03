---
id: ISSUE-0019
title: 出图工作台合并后，自由 prompt 与素材描述缺后端字段支撑
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: 前端        # 前端设计师 Dodo（image-web）
owner: 开发           # 球在开发：需评估并加后端字段
created: 2026-06-03
updated: 2026-06-03
related:
  - code: image-web/src/components/generate/GenerateStudio.tsx
  - code: image-web/docs/出图工作台-合并设计.md
  - code: image-code（ProjectGenerateRequest / CostPreview / AssetOut schema）
---

## 现象
「需求单 + 出图与选稿」已合并为「出图工作台」（GenerateStudio）。新版 hero 是一个大聊天框，
让用户用一句话描述想要的画面。但后端契约里有两处缺口，导致两个体验只能前端近似、无法落到出图：

1. **自由 prompt 未进出图入参**：`ProjectGenerateRequest` / `/generate/cost-preview` 没有自由文本字段。
   前端目前把聊天框文字仅持久化到 `brief.copy_text`，**不参与实际出图**——出图仍只由
   子场景/模板族/品类/档位/风格/尺寸/asset_ids 这套结构化参数驱动。
2. **素材无 prompt/描述字段**：产品交互希望「点参考图 → 回显其对应描述到聊天框」。但 `AssetOut`
   没有每图描述字段，前端只能用模板串近似（如“参考产品图#3 的构图与质感”），并非每图独立 prompt。

## 期望 vs 实际
- 期望：用户在聊天框写的描述能真正影响出图（喂给 gpt-image 的文本提示）；参考图能带各自描述供回显。
- 实际：描述只存档不影响出图；参考图回显为通用模板串。

## 需要后端（评估后实现）
1. 出图链路（`ProjectGenerateRequest` 及预估入参）增加**可选 `prompt`/`notes` 文本字段**，
   并在 gpt-image edits/generations 调用时拼入文本提示。
2. `AssetOut` 增加**可选 `description`/`prompt` 字段**（上传素材时可填或自动生成），供前端点选回显。

两项均为增强、非阻断；前端已按现有契约上线，后端补字段后前端再接（无需改前端结构，仅补传/读取）。

## 处理记录
- 2026-06-03 [前端] 出图工作台合并上线（接现有契约），创建本条记录后端缺口，状态=已确认，owner=开发
