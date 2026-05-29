# 品类画像 + 风格预设（Prompt 三维差异化）设计稿

| 项 | 内容 |
|---|---|
| 文档状态 | 待用户评审 |
| 起草日期 | 2026-05-29 |
| 范围 | A 阶段：在现有 Prompt 编排子系统上，新增「品类画像 + 风格预设」两个正交维度 |
| 后续 | C 阶段「族 × 品类细分覆盖」在本设计骨架上叠加，不推翻本设计 |
| 北极星 | **提高图生图命中率 / 结果不跑偏**——一切设计服务于此 |

---

## 0. 目标与非目标

**目标**
- 让"数码 vs 食品 vs 美妆"出图在镜头/构图/光型/防御上**按品类差异化**（品类画像）。
- 让"中国风 / 简约 / 轻奢 / 科技 / 清新"作为**可组合的调性层**（风格预设）。
- 修掉现有 orchestrator 的两个确定性缺陷（比例重复、质量词冗余）。
- 为下一期「图生图 edit 模式」预留**产品保真约束**接口（本期不实现真实调用）。

**非目标（本期不做，符合 PRD §3.4.10）**
- ❌ 运行时让 AI 即兴生成 Prompt（非确定性 = 跑偏，与北极星相悖）。风格预设走 **AI 起草 → 人工定稿 → 冻结固定库**，运行时确定性套用。
- ❌ 族 × 品类细分覆盖（C 阶段）。
- ❌ 真实模型调用 / 图生图 `/images/edits` 落地（紧随其后的独立一步）。

---

## 1. 三维模型与槽位归属（核心）

Prompt 由三个**正交**维度共同决定，每个维度有明确的"管辖槽位"，**杜绝两个维度抢同一槽**：

| 维度 | 含义 | 管辖槽位 | 实现 |
|---|---|---|---|
| **模板族** TemplateFamily | 句子结构骨架 | 骨架本身（族3/4/5/7） | 已有，不改结构 |
| **品类画像** CategoryProfile | "怎么拍这类东西"（物性/技法） | 镜头、构图、位置、角度、**光型**、品类道具(装饰元素)、防御词、品类负面、材质保真 | 本期新增 |
| **风格预设** StylePreset | "什么调性/审美"（调性/色彩） | 色卡、浅色A/B、**光色**、情绪基调(氛围词)、修饰风格词 | 本期新增 |

**冲突规避铁律**：品类与风格**永不写同一facet**。唯一同槽位的是「光影」，但拆成两个互不覆盖的侧面——**品类管光型（方向/硬度），风格管光色（色温/情绪）**，二者**拼接**生成最终光影描述，不是覆盖。

> 例：数码(光型=硬光勾勒金属边缘) × 轻奢(光色=暖金调) → `光影：硬光勾勒金属边缘，暖金色调`。

### 1.1 组合示例（你的核心场景）

| 品类画像 | × | 风格预设 | = 效果 |
|---|---|---|---|
| 数码（冷调科技镜头、金属保真） | × | 轻奢（黑金色卡、精致质感） | 轻奢风数码广告 |
| 食品（暖光、食材道具） | × | 中国风（国潮红金） | 国潮风食品广告 |
| 美妆（瓶身保真、柔焦） | × | 简约（北欧浅色） | 简约风美妆主图 |

---

## 2. 数据结构（application 层，纯数据/逻辑，无需端口）

> 与现有词库（color/guard/lens）同层级，是 application 内部可注册数据，不是外部依赖，故**不需要 port**；扩展靠注册表（OCP）。

```python
# application/prompt/profiles/category_profile.py
@dataclass(frozen=True)
class CategoryProfile:
    category: Category
    lens: str            # 镜头：数码"45°微距f/8深景深，金属反光可控"
    composition: str     # 构图：数码"居中正交，留白克制"
    position: str        # 位置："正中"
    angle: str           # 角度："正面平视" / "15°俯"
    light_form: str      # 光型(无色温)：数码"硬光勾勒边缘 + 柔光补面，控反光"
    props: str           # 品类道具/装饰：数码"极简几何垫块，无杂物"
    guard: str           # 防御词（取代 GuardLibrary）：数码"屏幕/按键位置不变..."
    negatives: tuple[str, ...]  # 品类负面侧重：数码"不要塑料感、不要错位接口"
    fidelity: str        # 材质保真侧重（图生图 edit 模式用，本期仅存储）

# application/prompt/profiles/style_preset.py
@dataclass(frozen=True)
class StylePreset:
    style: Style
    color_card: str      # 色卡HEX（取代 ColorLibrary）
    tint_a: str          # 浅色A（背景渐变起）
    tint_b: str          # 浅色B（背景渐变止）
    light_color: str     # 光色/色温情绪：轻奢"暖金调，低调奢华"
    mood: str            # 情绪基调(氛围词)：轻奢"高级静奢氛围"
    modifiers: tuple[str, ...]  # 修饰风格词：轻奢"精致质感、克制留白"
```

**注册表**（与 `FamilyRegistry` 同模式，OCP：新增品类/风格 = 加文件 + 注册，不改 orchestrator）：

```python
# application/prompt/profiles/registry.py
class CategoryProfileRegistry:
    def get(self, category: Category) -> CategoryProfile: ...  # 缺失 fail-fast 抛 KeyError

class StylePresetRegistry:
    def get(self, style: Style) -> StylePreset: ...
```

---

## 3. 现有词库的去留（清晰重构，无兼容层）

> 遵循 CLAUDE.md：旧代码适配新架构，不加 shim。

| 现有 | 处置 |
|---|---|
| `ColorLibrary`（色卡 by Style） | **移除**，数据迁入 `StylePreset.color_card` |
| `GuardLibrary`（防御 by Category） | **移除**，数据迁入 `CategoryProfile.guard` |
| `LensLibrary`（镜头 by LensPurpose） | **移除**（当前 orchestrator 根本没用它，镜头是写死的），词汇迁入各 `CategoryProfile.lens` |
| `NegativeLibrary`（负面） | **保留并瘦身**：只留「通用负面」+「族7节庆负面」；**品类负面**迁入 `CategoryProfile.negatives` |
| `QualityLibrary`（质量词 by Model） | **保留不变**（按模型，与品类/风格正交） |

---

## 4. orchestrator 改造

### 4.1 依赖变化（构造注入）
- 移除：`colors: ColorLibrary`、`guards: GuardLibrary`
- 新增：`categories: CategoryProfileRegistry`、`styles: StylePresetRegistry`
- 保留：`families`、`negatives`（瘦身版）、`qualities`、`vision`、`brands`

### 4.2 槽位填充：从"写死通用值"改为"画像 + 预设注入"

`_build_slots` 不再硬编码 `镜头="50mm..."`、`光影="侧上方柔和暖光"`、`氛围词="高级沉浸氛围"`，改为：

```
profile = categories.get(brief.category)
preset  = styles.get(brief.style)
slots = {
    "镜头": profile.lens,
    "构图": profile.composition,
    "位置": profile.position,
    "角度": profile.angle,
    "光影": f"{profile.light_form}，{preset.light_color}",   # 光型+光色拼接，不覆盖
    "装饰元素": profile.props,
    "氛围词": preset.mood,
    "色卡": preset.color_card,
    "浅色A": preset.tint_a, "浅色B": preset.tint_b,
    "风格": brief.style.value, "品类": brief.category.value,
    # 产品描述/品牌/标题/比例 等维持现状
}
```

`preset.modifiers`（修饰风格词）不进单个骨架槽，而由 orchestrator 在正向 prompt **收尾前**统一追加一句风格定调：`"风格修饰：{、连接的 modifiers}"`，紧挨质量词之前。这样修饰词作用于整图调性，且只出现一次。

### 4.3 防御词 / 负面来源切换
- 防御词：`profile.guard`（取代 `guards.get(category)`）
- 负面：`通用(NegativeLibrary) + profile.negatives + (族7时)节庆负面`，去重拼接
- 风格修饰：`preset.modifiers` 拼成一句风格定调，追加在质量词之前（见 §4.2 末）

### 4.4 修掉两个确定性缺陷
1. **比例重复**：骨架槽已含 `{比例}`，**移除** orchestrator 末尾再 append 的 `format_ratio`（line 51 那次）。最终只出现一次。
2. **质量词冗余**：族4 开头写死的 "8K超高清，电影级画质，极致细节" **下沉删除**，质量词**统一由 orchestrator 末尾按模型 append 一次**（`QualityLibrary`）。族4 骨架开头改为只保留 "超写实商业摄影质感" 之类非质量定调。

### 4.5 图生图保真预留接口（本期仅搭壳）
`build(brief, target_model, mode=GenMode.TEXT2IMG)` 增加 `mode` 参数：
- `TEXT2IMG`（本期默认）：行为同上。
- `EDIT`（下一期填实）：在正向 prompt 追加 `profile.fidelity` 保真约束段（"保持参考图产品主体/材质/Logo/比例完全不变，仅重绘背景与光影"）。本期定义 `GenMode` 枚举与分支占位，**不接真实模型**。

---

## 5. V1 覆盖范围

**品类画像（4 个）**：数码(DIGITAL_3C) / 食品(FOOD) / 美妆(BEAUTY) / 服饰(APPAREL)。
其余（含人物/镜面）未注册 → `get` 抛 KeyError（fail-fast），待后续补。

**风格预设（6 个）**：国潮中式 / 极简北欧(简约) / 高端轻奢 / 科技未来 / 清新自然 / 运动机能。
喜庆节日(FESTIVE) **不单列为风格**——它与「族7中式节庆」骨架强绑定，做成风格会与族7冲突，留给族7骨架处理。

> 4 品类 × 6 风格 × 4 模板族 = 理论 96 种组合，均由三维**正交组合**得到，无需逐一手写。
> 选型参考：市面电商 AI 工具（搞定/美图/爱创）的"风格预设"多为「风格+场景+模板」捆绑；拆解到本设计三维后，纯风格维度收敛到以上 6 个，"纯色背景/场景化"等属模板族而非风格。

---

## 6. 文件结构（落点）

```
application/prompt/
  profiles/                       # 新增
    __init__.py
    category_profile.py           # CategoryProfile dataclass
    style_preset.py               # StylePreset dataclass
    categories/                   # 4 个品类画像，一品类一文件(SRP)
      digital.py food.py beauty.py apparel.py
    styles/                       # 6 个风格预设，一风格一文件(SRP)
      guochao.py nordic.py luxury.py tech.py fresh.py sport.py
    registry.py                   # CategoryProfileRegistry + StylePresetRegistry
  libraries/
    color.py  guard.py  lens.py   # 移除
    negative.py                   # 瘦身(通用+节庆)
    quality.py                    # 不变
  rules.py  brand.py  orchestrator.py  # orchestrator 改造；rules 增 GenMode
  vision.py(已在 ports)
domain/enums.py                   # 新增 GenMode(TEXT2IMG/EDIT)
composition.py                    # build_orchestrator 装配改为注入两个 registry
```

---

## 7. SOLID 对照

- **SRP**：一品类一文件、一风格一文件、一职责（画像只管物性、预设只管调性）。
- **OCP**：新增品类/风格 = 加文件 + 注册，**不改 orchestrator**；C 阶段(族×品类)叠加亦不改本结构。
- **LSP**：注册表取出的 Profile/Preset 同构可替换。
- **ISP**：CategoryProfile / StylePreset 字段各自内聚，互不牵连。
- **DIP**：orchestrator 依赖两个 Registry 抽象（构造注入），不依赖具体品类/风格文件。

---

## 8. 验收（Dev 角色不写测试，用 smoke 自检；测试归 QA）

- 数码×轻奢×族4：成品含"金属/冷调镜头 + 暖金光色 + 数码防御词"，**比例只出现一次**，**质量词只出现一次**。
- 食品×中国风×族5：成品含"暖光食材道具 + 国潮红金色卡 + 食品负面(不要塑料感)"。
- 未注册品类(镜面)：`get` 抛 KeyError。
- `mode=EDIT`：正向 prompt 末尾出现保真约束段（占位字符串）。
- ruff + mypy strict 全绿。

---

## 9. 后续衔接

1. 本设计实现完 → 接 gpt-image-2 真实 API → 落地图生图 `/images/edits`，把 §4.5 的 `EDIT` 模式 + `profile.fidelity` 填实，真实验证命中率。
2. C 阶段：在 `profiles/` 上加 `(family, category)` 覆盖层，不改三维主结构。

---

**文档结束。**
