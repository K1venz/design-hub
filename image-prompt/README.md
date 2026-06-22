# image-prompt · 提示词工程

> 角色:资深产品图提示词工程师(新增主动角色)。
> 写边界:**只写本文件夹 + image-issues**;PRD(image-prd)、代码(image-code)对我只读,要它们改 → 开 issue。
> 北极星:让 gpt-image-2 出的图 **真实、不像 AI、品牌不跑偏、产品不被乱改**,且多品类通用。

## 体系:宪章 + 卡 + Agent 组装

把现状的"确定性字符串拼接"演进为"**LLM agent 按指令组装 prompt**"。三层指令架构:

```
[通用宪章 00-charter.md]          永远注入 · 角色/北极星/gpt-image-2铁律/输出契约/自检
        +  [品类卡 category-cards/]   按品类注入一张 · 物性/失真命门/保真清单/真实感线索
        +  [风格卡 style-cards/]       按调性注入一张 · 色卡/光色/情绪
        +  [需求单 + 视觉理解产物]
        ↓  agent 组装(消重/排序/正向化/前置命门) → prompt → 自检 → 输出
```

**多品类扩展 = 加一张品类卡**(照 `category-cards/_schema.md` 写),宪章与代码一字不改(OCP)。

## 目录
| 路径 | 作用 |
|---|---|
| [`00-charter.md`](./00-charter.md) | 通用宪章(agent system prompt 本体) |
| [`category-cards/_schema.md`](./category-cards/_schema.md) | 品类卡写法(多品类扩展入口) |
| [`category-cards/food/通用.md`](./category-cards/food/通用.md) | FOOD 默认卡(产品中性、MVP wired 源) |
| [`category-cards/food/peanut.md`](./category-cards/food/peanut.md) | 花生产品卡(backlog、未挂、仅真做花生时套) |
| [`image-type-cards/_schema.md`](./image-type-cards/_schema.md) | 图型卡写法(第四类卡,套图用,与品类卡正交) |
| [`image-type-cards/`](./image-type-cards/) 白底/场景/卖点 | MVP 3 张图型卡(PRD §3.12.14,中文枚举 key) |
| [`套图-图型卡体系草案.md`](./套图-图型卡体系草案.md) | 套图提示词层设计决策记录 |
| [`clone-mode-cards/复刻.md`](./clone-mode-cards/复刻.md) | 复刻模式卡(第五类卡,两档:参考风格/完全复刻;完全复刻=三贴一隔+overlay 无字/有字双块) |
| [`edit-mode-cards/编辑.md`](./edit-mode-cards/编辑.md) | 编辑模式卡(第六类卡,两档:delta 微调/full 重做) |
| [`二次编辑-编辑模式草案.md`](./二次编辑-编辑模式草案.md) | 二次编辑提示词层设计决策记录 |
| [`爆款复刻-两档指令草案.md`](./爆款复刻-两档指令草案.md) | 复刻提示词层设计决策记录 |
| [`style-cards/_schema.md`](./style-cards/_schema.md) | 风格卡写法 |
| [`style-cards/fresh-natural.md`](./style-cards/fresh-natural.md) | 清新自然风格卡 |
| [`examples/花生-端到端.md`](./examples/花生-端到端.md) | 端到端示例 + 现状代码对照 |
| [`references/gpt-image-2-能力边界.md`](./references/gpt-image-2-能力边界.md) | 模型能力边界一手调研 |

## 进度
- 2026-06-01 建立角色与体系骨架:宪章 + 花生品类卡 + 清新风格卡 + 端到端示例 + 能力边界调研。
- 2026-06-01 开 ISSUE-0006:请 Dev 将 orchestrator 演进为"宪章+卡+agent 组装",并修正现状 7 个反模式。
- 待办:补 food-通用/digital/beauty/apparel 品类卡;补其余风格卡;落"自检对抗回路(丙)"于精修档。
