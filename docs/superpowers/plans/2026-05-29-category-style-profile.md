# 品类画像 + 风格预设 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development 或 superpowers:executing-plans 逐任务实施。步骤用 `- [ ]` 跟踪。
> **Dev 角色适配**：本仓库 `image-code/CLAUDE.md` 规定本窗口不写测试用例（测试归 QA）。故各任务用 `uv run python -c` smoke 自检 + ruff + mypy strict 验证，不落 pytest 文件。所有命令在 `image-code/` 下执行。

**Goal:** 在现有 Prompt 编排子系统上新增「品类画像 + 风格预设」两个正交维度，让数码/食品/美妆/服饰 × 国潮/简约/轻奢/科技/清新/运动 可正交组合，并修掉比例重复、质量词冗余两个缺陷，预留图生图 EDIT 保真接口。

**Architecture:** 新增 `application/prompt/profiles/`：CategoryProfile（物性：镜头/构图/光型/防御/保真）+ StylePreset（调性：色卡/光色/情绪/修饰词），各自注册表（OCP）。orchestrator 改为从两个注册表注入槽位值，取代写死默认值与 Color/Guard/Lens 词库（清理无 shim）。光影按"光型(品类)+光色(风格)"拼接不覆盖。

**Tech Stack:** Python 3.12 · uv · dataclass(frozen) · 现有 design_hub 六边形结构。

依据规格：`docs/superpowers/specs/2026-05-29-category-style-profile-design.md`。

---

## 文件结构（落点）

```
src/design_hub/
  domain/enums.py                              # 修改：新增 GenMode
  application/prompt/
    profiles/
      __init__.py                              # 新增
      category_profile.py                      # 新增 CategoryProfile
      style_preset.py                          # 新增 StylePreset
      categories/{__init__,digital,food,beauty,apparel}.py   # 新增 4 品类画像
      styles/{__init__,guochao,nordic,luxury,tech,fresh,sport}.py  # 新增 6 风格预设
      registry.py                              # 新增 两个注册表
    libraries/
      color.py guard.py lens.py                # 删除
      negative.py                              # 修改：瘦身为 common()+festive()
      quality.py                               # 不变
    families/family4.py                        # 修改：去掉开头写死的质量词
    orchestrator.py                            # 修改：注入注册表、改填槽、修两个缺陷、加 mode
  composition.py                               # 修改：build_orchestrator 装配
```

---

## Task 1: 新增 GenMode 枚举

**Files:** Modify `src/design_hub/domain/enums.py`

- [ ] **Step 1: 追加枚举**

在 `src/design_hub/domain/enums.py` 末尾追加：

```python
class GenMode(StrEnum):
    TEXT2IMG = "text2img"  # 文生图/造景
    EDIT = "edit"          # 图生图 edit（保持产品不变，仅重绘背景光影）
```

- [ ] **Step 2: smoke 验证**

Run: `uv run python -c "from design_hub.domain.enums import GenMode; assert GenMode.EDIT.value=='edit'; print('GenMode OK')"`
Expected: `GenMode OK`

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/domain/enums.py
git commit -m "feat: 新增 GenMode 枚举(文生图/图生图edit)"
```

---

## Task 2: CategoryProfile 与 StylePreset 数据结构

**Files:** Create `src/design_hub/application/prompt/profiles/__init__.py`、`category_profile.py`、`style_preset.py`

- [ ] **Step 1: 建空 `__init__.py`**

Create `src/design_hub/application/prompt/profiles/__init__.py`（空文件）。

- [ ] **Step 2: CategoryProfile**

Create `src/design_hub/application/prompt/profiles/category_profile.py`:

```python
from dataclasses import dataclass

from design_hub.domain.enums import Category


@dataclass(frozen=True)
class CategoryProfile:
    """品类画像（物性/技法）：怎么拍这类东西。"""

    category: Category
    lens: str  # 镜头
    composition: str  # 构图
    position: str  # 位置
    angle: str  # 角度
    light_form: str  # 光型（方向/硬度，不含色温）
    props: str  # 品类道具/装饰
    guard: str  # 防御词（材质保真/防漂移）
    negatives: tuple[str, ...]  # 品类负面侧重
    fidelity: str  # 材质保真侧重（图生图 EDIT 模式用）
```

- [ ] **Step 3: StylePreset**

Create `src/design_hub/application/prompt/profiles/style_preset.py`:

```python
from dataclasses import dataclass

from design_hub.domain.enums import Style


@dataclass(frozen=True)
class StylePreset:
    """风格预设（调性/色彩）：什么审美。AI 起草→人工定稿→冻结固定库。"""

    style: Style
    color_card: str  # 色卡 HEX
    tint_a: str  # 浅色A（背景渐变起）
    tint_b: str  # 浅色B（背景渐变止）
    light_color: str  # 光色/色温情绪
    mood: str  # 情绪基调（氛围词）
    modifiers: tuple[str, ...]  # 修饰风格词
```

- [ ] **Step 4: smoke 验证**

Run:
```bash
uv run python -c "
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Category, Style
c=CategoryProfile(category=Category.FOOD,lens='l',composition='c',position='p',angle='a',light_form='lf',props='pr',guard='g',negatives=('n',),fidelity='f')
s=StylePreset(style=Style.LUXURY,color_card='cc',tint_a='ta',tint_b='tb',light_color='lc',mood='m',modifiers=('mod',))
assert c.category is Category.FOOD and s.style is Style.LUXURY
print('dataclasses OK')
"
```
Expected: `dataclasses OK`

- [ ] **Step 5: 提交**

```bash
git add src/design_hub/application/prompt/profiles/__init__.py src/design_hub/application/prompt/profiles/category_profile.py src/design_hub/application/prompt/profiles/style_preset.py
git commit -m "feat: CategoryProfile/StylePreset 数据结构(SRP)"
```

---

## Task 3: 4 个品类画像

**Files:** Create `categories/__init__.py`、`digital.py`、`food.py`、`beauty.py`、`apparel.py`

- [ ] **Step 1: 建空 `__init__.py`**

Create `src/design_hub/application/prompt/profiles/categories/__init__.py`（空文件）。

- [ ] **Step 2: 数码**

Create `src/design_hub/application/prompt/profiles/categories/digital.py`:

```python
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

DIGITAL = CategoryProfile(
    category=Category.DIGITAL_3C,
    lens="45°微距，f/8 深景深，控制金属反光",
    composition="居中正交构图，留白克制，重心沉稳",
    position="正中",
    angle="正面平视微俯",
    light_form="硬光勾勒金属边缘，柔光补面，反光可控",
    props="极简几何垫块，深色磨砂台面，无杂物",
    guard="严格保持产品外观结构比例不变；屏幕/按键/接口位置不变；金属与玻璃质感真实",
    negatives=("不要塑料廉价感", "不要错位接口", "不要多余按键"),
    fidelity="保持参考图数码产品的机身线条、屏幕内容、按键与接口布局、Logo 完全不变，仅重绘环境光影",
)
```

- [ ] **Step 3: 食品**

Create `src/design_hub/application/prompt/profiles/categories/food.py`:

```python
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

FOOD = CategoryProfile(
    category=Category.FOOD,
    lens="50mm，f/2.8 近景，自然食欲色彩",
    composition="45°俯拍或平视，主体置黄金分割点，留白透气",
    position="画面视觉重心",
    angle="45°俯",
    light_form="侧逆暖光勾轮廓，柔和补光，营造食欲高光",
    props="新鲜食材点缀、餐布或木台、相关原料散落",
    guard="保留食品原色与质地；包装文字清晰；不夸大不失真",
    negatives=("不要塑料感", "不要假食物感", "不要过度调色"),
    fidelity="保持参考图食品/包装的形态、配色、文字与质地完全不变，仅重绘场景与光氛围",
)
```

- [ ] **Step 4: 美妆**

Create `src/design_hub/application/prompt/profiles/categories/beauty.py`:

```python
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

BEAUTY = CategoryProfile(
    category=Category.BEAUTY,
    lens="85mm，f/4，柔焦近景，瓶身高光干净",
    composition="居中或对称，留充足文案空间",
    position="正中偏上",
    angle="正面平视",
    light_form="柔光箱均匀布光，瓶身边缘高光，倒影干净",
    props="水波、丝绸或花瓣等柔质点缀，呼应成分",
    guard="瓶身比例不变；Logo/标签文字清晰；瓶盖结构完整",
    negatives=("不要标签文字模糊", "不要瓶型变形", "不要廉价塑料反光"),
    fidelity="保持参考图美妆瓶身的轮廓、标签文字、Logo、瓶盖结构完全不变，仅重绘背景与光影",
)
```

- [ ] **Step 5: 服饰**

Create `src/design_hub/application/prompt/profiles/categories/apparel.py`:

```python
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.domain.enums import Category

APPAREL = CategoryProfile(
    category=Category.APPAREL,
    lens="35mm，f/5.6，平铺或挂拍，纹理清晰",
    composition="居中平铺或立体悬挂，留白均衡",
    position="正中",
    angle="正面平视",
    light_form="大面积柔光，斜侧光强调面料纹理与褶皱立体",
    props="极简衣架或台面，少量配饰呼应",
    guard="手指/道具不遮挡核心结构；面料纹理清晰；五金件高光突出",
    negatives=("不要面料失真", "不要褶皱杂乱", "不要廉价化纤反光"),
    fidelity="保持参考图服饰的版型、面料纹理、颜色、印花与五金件完全不变，仅重绘背景与光影",
)
```

- [ ] **Step 6: smoke 验证**

Run:
```bash
uv run python -c "
from design_hub.application.prompt.profiles.categories.digital import DIGITAL
from design_hub.application.prompt.profiles.categories.food import FOOD
from design_hub.application.prompt.profiles.categories.beauty import BEAUTY
from design_hub.application.prompt.profiles.categories.apparel import APPAREL
from design_hub.domain.enums import Category
got={p.category for p in (DIGITAL,FOOD,BEAUTY,APPAREL)}
assert got=={Category.DIGITAL_3C,Category.FOOD,Category.BEAUTY,Category.APPAREL}
assert '金属' in DIGITAL.light_form and '食欲' in FOOD.light_form
print('4 category profiles OK')
"
```
Expected: `4 category profiles OK`

- [ ] **Step 7: 提交**

```bash
git add src/design_hub/application/prompt/profiles/categories
git commit -m "feat: 4 个品类画像(数码/食品/美妆/服饰, 一品类一文件 SRP)"
```

---

## Task 4: 6 个风格预设

**Files:** Create `styles/__init__.py`、`guochao.py`、`nordic.py`、`luxury.py`、`tech.py`、`fresh.py`、`sport.py`

- [ ] **Step 1: 建空 `__init__.py`**

Create `src/design_hub/application/prompt/profiles/styles/__init__.py`（空文件）。

- [ ] **Step 2: 国潮中式**

Create `src/design_hub/application/prompt/profiles/styles/guochao.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

GUOCHAO = StylePreset(
    style=Style.GUOCHAO,
    color_card="中国红 #E60012 + 鎏金 #d4af37 + 墨黑 #1c1c1c",
    tint_a="暖米白",
    tint_b="浅金",
    light_color="暖金色调，红金辉映",
    mood="国潮喜庆、东方韵味",
    modifiers=("祥云回纹点缀", "鎏金质感", "新中式审美"),
)
```

- [ ] **Step 3: 极简北欧**

Create `src/design_hub/application/prompt/profiles/styles/nordic.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

NORDIC = StylePreset(
    style=Style.NORDIC,
    color_card="鼠尾草绿 #b2c2a8 + 牛皮纸 #d4c4a0 + 奶油白 #f5f0e6",
    tint_a="奶油白",
    tint_b="浅燕麦",
    light_color="自然柔光，中性色温",
    mood="极简克制、留白通透",
    modifiers=("大量留白", "极简构成", "ins 北欧风"),
)
```

- [ ] **Step 4: 高端轻奢**

Create `src/design_hub/application/prompt/profiles/styles/luxury.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

LUXURY = StylePreset(
    style=Style.LUXURY,
    color_card="黑金 #1a1a1a + 暖金 #c9a86a + 深红 #6b2020",
    tint_a="深空灰",
    tint_b="墨黑",
    light_color="暖金低调光，明暗对比强",
    mood="高级静奢、精致沉稳",
    modifiers=("精致质感", "克制奢华", "杂志大片感"),
)
```

- [ ] **Step 5: 科技未来**

Create `src/design_hub/application/prompt/profiles/styles/tech.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

TECH = StylePreset(
    style=Style.TECH,
    color_card="深空蓝 #0a1428 + 电光紫 #8b5cf6 + 冷银 #c0c8d0",
    tint_a="冷灰",
    tint_b="深蓝黑",
    light_color="冷调光，蓝紫氛围光",
    mood="未来科技、冷峻精密",
    modifiers=("光效线条", "金属冷光", "科技感"),
)
```

- [ ] **Step 6: 清新自然**

Create `src/design_hub/application/prompt/profiles/styles/fresh.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

FRESH = StylePreset(
    style=Style.FRESH,
    color_card="薄荷绿 #a8d8c0 + 浅木色 #d9c9b0 + 白 #ffffff",
    tint_a="薄荷白",
    tint_b="浅木",
    light_color="明亮自然光，清透色温",
    mood="清新自然、轻盈通透",
    modifiers=("自然光感", "清透通透", "小清新"),
)
```

- [ ] **Step 7: 运动机能**

Create `src/design_hub/application/prompt/profiles/styles/sport.py`:

```python
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.domain.enums import Style

SPORT = StylePreset(
    style=Style.SPORT,
    color_card="电光橙 #ff6b1a + 冷灰 #4a5057 + 黑 #1a1a1a",
    tint_a="冷灰",
    tint_b="炭黑",
    light_color="高对比硬光，冷暖撞色",
    mood="动感机能、力量潮酷",
    modifiers=("动感线条", "机能质感", "潮酷撞色"),
)
```

- [ ] **Step 8: smoke 验证**

Run:
```bash
uv run python -c "
from design_hub.application.prompt.profiles.styles.guochao import GUOCHAO
from design_hub.application.prompt.profiles.styles.nordic import NORDIC
from design_hub.application.prompt.profiles.styles.luxury import LUXURY
from design_hub.application.prompt.profiles.styles.tech import TECH
from design_hub.application.prompt.profiles.styles.fresh import FRESH
from design_hub.application.prompt.profiles.styles.sport import SPORT
from design_hub.domain.enums import Style
got={p.style for p in (GUOCHAO,NORDIC,LUXURY,TECH,FRESH,SPORT)}
assert len(got)==6 and Style.SPORT in got
assert '#E60012' in GUOCHAO.color_card
print('6 style presets OK')
"
```
Expected: `6 style presets OK`

- [ ] **Step 9: 提交**

```bash
git add src/design_hub/application/prompt/profiles/styles
git commit -m "feat: 6 个风格预设(国潮/简约/轻奢/科技/清新/运动, 一风格一文件 SRP)"
```

---

## Task 5: 两个注册表

**Files:** Create `src/design_hub/application/prompt/profiles/registry.py`

- [ ] **Step 1: 注册表**

Create `src/design_hub/application/prompt/profiles/registry.py`:

```python
from design_hub.application.prompt.profiles.categories.apparel import APPAREL
from design_hub.application.prompt.profiles.categories.beauty import BEAUTY
from design_hub.application.prompt.profiles.categories.digital import DIGITAL
from design_hub.application.prompt.profiles.categories.food import FOOD
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.application.prompt.profiles.styles.fresh import FRESH
from design_hub.application.prompt.profiles.styles.guochao import GUOCHAO
from design_hub.application.prompt.profiles.styles.luxury import LUXURY
from design_hub.application.prompt.profiles.styles.nordic import NORDIC
from design_hub.application.prompt.profiles.styles.sport import SPORT
from design_hub.application.prompt.profiles.styles.tech import TECH
from design_hub.domain.enums import Category, Style


class CategoryProfileRegistry:
    """V1 内置 4 品类画像；未注册品类 fail-fast。"""

    def __init__(self) -> None:
        self._profiles: dict[Category, CategoryProfile] = {}
        for profile in (DIGITAL, FOOD, BEAUTY, APPAREL):
            self._profiles[profile.category] = profile

    def get(self, category: Category) -> CategoryProfile:
        if category not in self._profiles:
            raise KeyError(f"No category profile for {category}")
        return self._profiles[category]


class StylePresetRegistry:
    """V1 内置 6 风格预设；未注册风格 fail-fast。"""

    def __init__(self) -> None:
        self._presets: dict[Style, StylePreset] = {}
        for preset in (GUOCHAO, NORDIC, LUXURY, TECH, FRESH, SPORT):
            self._presets[preset.style] = preset

    def get(self, style: Style) -> StylePreset:
        if style not in self._presets:
            raise KeyError(f"No style preset for {style}")
        return self._presets[style]
```

- [ ] **Step 2: smoke 验证**

Run:
```bash
uv run python -c "
from design_hub.application.prompt.profiles.registry import CategoryProfileRegistry, StylePresetRegistry
from design_hub.domain.enums import Category, Style
cr=CategoryProfileRegistry(); sr=StylePresetRegistry()
assert cr.get(Category.DIGITAL_3C).category is Category.DIGITAL_3C
assert sr.get(Style.SPORT).style is Style.SPORT
try: cr.get(Category.MIRROR); raise SystemExit('mirror should fail')
except KeyError: pass
print('registries OK')
"
```
Expected: `registries OK`

- [ ] **Step 3: 提交**

```bash
git add src/design_hub/application/prompt/profiles/registry.py
git commit -m "feat: 品类画像/风格预设注册表(OCP, 未注册 fail-fast)"
```

---

## Task 6: orchestrator 切换 + 清理旧词库 + 修缺陷（核心，一次切换保持绿）

**Files:**
- Modify `src/design_hub/application/prompt/libraries/negative.py`（瘦身）
- Delete `src/design_hub/application/prompt/libraries/color.py`、`guard.py`、`lens.py`
- Modify `src/design_hub/application/prompt/families/family4.py`（去质量词）
- Modify `src/design_hub/application/prompt/orchestrator.py`（重写）
- Modify `src/design_hub/composition.py`（装配）

> 本任务是跨文件切换，必须整体完成才能保持可运行（无 shim，符合 CLAUDE.md）。

- [ ] **Step 1: 瘦身 NegativeLibrary**

覆盖 `src/design_hub/application/prompt/libraries/negative.py`:

```python
from design_hub.domain.enums import TemplateFamily

_COMMON = ["不要廉价电商风", "不要过度设计", "不要杂乱", "不要 AI 廉价感"]
_FESTIVE = ["不要俗气红", "不要复古酒吧风"]


class NegativeLibrary:
    """词库 B：通用负面 + 族7节庆负面。品类负面已迁入 CategoryProfile。"""

    def common(self) -> list[str]:
        return list(_COMMON)

    def for_family(self, family: TemplateFamily) -> list[str]:
        return list(_FESTIVE) if family is TemplateFamily.F7 else []
```

- [ ] **Step 2: 删除三个旧词库**

```bash
git rm src/design_hub/application/prompt/libraries/color.py src/design_hub/application/prompt/libraries/guard.py src/design_hub/application/prompt/libraries/lens.py
```

- [ ] **Step 3: 去掉 family4 写死的质量词**

修改 `src/design_hub/application/prompt/families/family4.py` 的 `render` 返回值首句——把：

```python
            "8K超高清，电影级画质，极致细节。超写实3D渲染，商业摄影质感。"
```

改为：

```python
            "超写实商业摄影质感。"
```

（其余行不变。质量词改由 orchestrator 末尾按模型统一追加一次。）

- [ ] **Step 4: 重写 orchestrator**

覆盖 `src/design_hub/application/prompt/orchestrator.py`:

```python
from design_hub.application.prompt.brand import BrandNameGenerator
from design_hub.application.prompt.families.registry import FamilyRegistry
from design_hub.application.prompt.libraries.negative import NegativeLibrary
from design_hub.application.prompt.libraries.quality import QualityLibrary
from design_hub.application.prompt.profiles.category_profile import CategoryProfile
from design_hub.application.prompt.profiles.registry import (
    CategoryProfileRegistry,
    StylePresetRegistry,
)
from design_hub.application.prompt.profiles.style_preset import StylePreset
from design_hub.application.prompt.rules import format_ratio, typography_block
from design_hub.domain.enums import GenMode, ModelName, TemplateFamily
from design_hub.domain.models import Brief, PromptPair
from design_hub.ports.vision import VisionAssist


class PromptOrchestrator:
    """编排器（DIP）：组合注入族/品类画像/风格预设/词库/视觉/品牌。

    三维正交：模板族(骨架) × 品类画像(物性) × 风格预设(调性)。
    光影按"光型(品类)+光色(风格)"拼接，不覆盖。
    """

    def __init__(
        self,
        *,
        families: FamilyRegistry,
        categories: CategoryProfileRegistry,
        styles: StylePresetRegistry,
        negatives: NegativeLibrary,
        qualities: QualityLibrary,
        vision: VisionAssist,
        brands: BrandNameGenerator,
    ) -> None:
        self._families = families
        self._categories = categories
        self._styles = styles
        self._negatives = negatives
        self._qualities = qualities
        self._vision = vision
        self._brands = brands

    async def build(
        self,
        brief: Brief,
        target_model: ModelName,
        mode: GenMode = GenMode.TEXT2IMG,
    ) -> PromptPair:
        profile = self._categories.get(brief.category)
        preset = self._styles.get(brief.style)

        product_desc = brief.product_desc
        if product_desc is None:
            info = await self._vision.analyze(list(brief.reference_images))
            product_desc = (
                f"{info.material}{info.product_type}，主色{info.main_color_hex}，{info.shape_ratio}"
            )

        slots = self._build_slots(brief, profile, preset, product_desc, target_model)
        positive = self._families.get(brief.family).render(slots)

        # 法则4 防御词
        positive += "。" + profile.guard
        # 法则6 文字独立段
        positive += typography_block(brief.copy_text)
        # 图生图 EDIT：追加产品保真约束
        if mode is GenMode.EDIT:
            positive += "。" + profile.fidelity
        # 风格修饰（preset.modifiers，整图调性，仅一次）
        positive += "。风格修饰：" + "、".join(preset.modifiers)
        # 法则10 质量词（按模型，仅一次；比例已由骨架槽承担，不再追加）
        positive += "。" + self._qualities.get(target_model)

        negative_items = self._negatives.common()
        negative_items += list(profile.negatives)
        negative_items += self._negatives.for_family(brief.family)
        negative = "、".join(dict.fromkeys(negative_items))  # 去重保序
        return PromptPair(positive=positive, negative=negative)

    def _build_slots(
        self,
        brief: Brief,
        profile: CategoryProfile,
        preset: StylePreset,
        product_desc: str,
        target_model: ModelName,
    ) -> dict[str, str]:
        ratio = format_ratio(brief.size, target_model)
        brand = brief.brand_name or self._brands.candidates(brief.category, 1)[0]
        title = brief.copy_text or f"{brand} 臻选"
        return {
            "风格": brief.style.value,
            "品类": brief.category.value,
            "产品描述": product_desc,
            "色卡": preset.color_card,
            "比例": ratio,
            "品牌": brand,
            # 品类画像（物性）
            "位置": profile.position,
            "角度": profile.angle,
            "镜头": profile.lens,
            "构图": profile.composition,
            "装饰元素": profile.props,
            # 光影 = 光型(品类) + 光色(风格)，拼接不覆盖
            "光影": f"{profile.light_form}，{preset.light_color}",
            # 风格预设（调性）
            "浅色A": preset.tint_a,
            "浅色B": preset.tint_b,
            "氛围词": preset.mood,
            # 文案类
            "标题文案": title,
            "产品名": product_desc,
            "主标题": title,
            "促销标语": brief.copy_text or "限时优惠",
            "主题场景名": "新春",
            "搜索词": brand,
            "用途": f"电商{brief.category.value}广告主图",
        }
```

- [ ] **Step 5: 更新 composition 装配**

修改 `src/design_hub/composition.py` 的 `build_orchestrator`。把原来的：

```python
from design_hub.application.prompt.libraries.color import ColorLibrary
from design_hub.application.prompt.libraries.guard import GuardLibrary
```
等导入与构造改为：

```python
def build_orchestrator() -> PromptOrchestrator:
    return PromptOrchestrator(
        families=FamilyRegistry(),
        categories=CategoryProfileRegistry(),
        styles=StylePresetRegistry(),
        negatives=NegativeLibrary(),
        qualities=QualityLibrary(),
        vision=MockVisionAssist(),
        brands=BrandNameGenerator(),
    )
```

并把顶部 import 中的 `ColorLibrary`、`GuardLibrary` 行删除，新增：

```python
from design_hub.application.prompt.profiles.registry import (
    CategoryProfileRegistry,
    StylePresetRegistry,
)
```

（`FamilyRegistry`、`NegativeLibrary`、`QualityLibrary`、`MockVisionAssist`、`BrandNameGenerator` 的 import 保留不变。）

- [ ] **Step 6: ruff + mypy**

Run: `uv run ruff check src && uv run mypy`
Expected: ruff `All checks passed!`；mypy `Success`（如报未用 import 或缺 import，按提示清理）。

- [ ] **Step 7: 全链路 smoke 验证**

Run:
```bash
uv run python -c "
import asyncio
from design_hub.composition import build_orchestrator
from design_hub.domain.enums import Category, GenMode, ModelName, Style, SubScene, TemplateFamily, Tier
from design_hub.domain.models import Brief
orch=build_orchestrator()
def brief(**kw):
    base=dict(customer='客户A',subscene=SubScene.S1,family=TemplateFamily.F4,tier=Tier.STANDARD,style=Style.LUXURY,category=Category.DIGITAL_3C,size=(1024,1536)); base.update(kw); return Brief(**base)
async def main():
    # 数码×轻奢×族4：品类光型 + 风格光色拼接、防御词、比例只一次、质量词只一次
    p=await orch.build(brief(), ModelName.GPT_IMAGE_2)
    assert '金属边缘' in p.positive and '暖金' in p.positive, p.positive
    assert p.positive.count('2:3竖版')==1, p.positive
    assert p.positive.count('8K超高清')==1, p.positive
    assert '屏幕/按键/接口位置不变' in p.positive
    assert '风格修饰：' in p.positive and '克制奢华' in p.positive
    assert '不要塑料廉价感' in p.negative and '不要 AI 廉价感' in p.negative
    # 食品×国潮×族5（族5 无光影槽，校验其真实会用到的：装饰道具=食材、色卡、食品防御/负面）
    p2=await orch.build(brief(family=TemplateFamily.F5,style=Style.GUOCHAO,category=Category.FOOD), ModelName.QWEN_IMAGE_PRO)
    assert '食材' in p2.positive and '#E60012' in p2.positive
    assert '保留食品原色' in p2.positive and '不要假食物感' in p2.negative
    # EDIT 模式追加保真段
    p3=await orch.build(brief(), ModelName.GPT_IMAGE_2, GenMode.EDIT)
    assert '仅重绘环境光影' in p3.positive
    # 未注册品类 fail-fast
    try: await orch.build(brief(category=Category.MIRROR), ModelName.GPT_IMAGE_2); raise SystemExit('mirror should fail')
    except KeyError: pass
    print('orchestrator 三维 smoke 全部通过')
asyncio.run(main())
"
```
Expected: `orchestrator 三维 smoke 全部通过`

- [ ] **Step 8: 提交**

```bash
git add src/design_hub/application/prompt/orchestrator.py src/design_hub/application/prompt/libraries/negative.py src/design_hub/application/prompt/families/family4.py src/design_hub/composition.py
git commit -m "refactor: orchestrator 接入品类画像+风格预设三维(SOLID)

槽位默认值从写死改为画像/预设注入；光影=光型(品类)+光色(风格)拼接；
防御词/品类负面来自画像；风格修饰来自预设；新增 GenMode EDIT 追加
保真约束。修复比例重复、质量词冗余两个缺陷。清理 Color/Guard/Lens
词库(无 shim)，NegativeLibrary 瘦身为通用+节庆。composition 装配更新。"
```

---

## Task 7: 进度文档与 issue 收尾

**Files:** Modify `docs/工期与进度跟踪.md`

- [ ] **Step 1: 进度日志追加一行**

在 `docs/工期与进度跟踪.md` 的「进度日志」表末尾追加：

```
| 2026-05-29 | 提示词三维差异化 | 品类画像(4)+风格预设(6)正交接入 orchestrator，修比例/质量词缺陷，预留图生图 EDIT 保真接口 | (本次提交) |
```

- [ ] **Step 2: 提交**

```bash
git add "docs/工期与进度跟踪.md"
git commit -m "docs: 进度日志记录提示词三维差异化完成"
```

---

## Self-Review（规格覆盖核对）

| 规格要求（design 稿） | 对应任务 |
|---|---|
| GenMode 枚举（§4.5） | Task 1 |
| CategoryProfile/StylePreset 结构（§2） | Task 2 |
| 4 品类画像（§5） | Task 3 |
| 6 风格预设（§5，含运动机能） | Task 4 |
| 两个注册表 OCP（§2） | Task 5 |
| 槽位归属：品类管镜头/构图/光型/防御/道具（§1） | Task 6 Step 4 `_build_slots` |
| 槽位归属：风格管色卡/浅色/光色/情绪/修饰（§1） | Task 6 Step 4 |
| 光影=光型+光色拼接不覆盖（§1 铁律） | Task 6 Step 4 `光影` 行 |
| modifiers 收尾追加一次（§4.2 末） | Task 6 Step 4 `风格修饰` 行 |
| 防御/负面来源切换（§4.3） | Task 6 Step 1+4 |
| 清理 Color/Guard/Lens 无 shim（§3） | Task 6 Step 2 |
| NegativeLibrary 瘦身（§3） | Task 6 Step 1 |
| 修比例重复（§4.4） | Task 6 Step 4（不再尾部追加 format_ratio） |
| 修质量词冗余（§4.4） | Task 6 Step 3+4（family4 去质量词，orchestrator 尾部一次） |
| EDIT 模式保真段（§4.5） | Task 6 Step 4 `mode is GenMode.EDIT` |
| V1 覆盖 4 品类×6 风格（§5） | Task 3 + Task 4 |
| SOLID（§7） | 全程：一文件一职责、注册表 OCP、构造注入 DIP |

**类型一致性核对**：`CategoryProfile`/`StylePreset` 字段（Task 2）与 Task 3/4 构造、Task 6 引用（`profile.lens`/`preset.color_card`/`profile.light_form`/`preset.light_color`/`profile.guard`/`profile.negatives`/`profile.fidelity`/`preset.modifiers`/`preset.mood`/`preset.tint_a/b`）全部一致；`NegativeLibrary.common()`/`for_family()`（Task 6 Step 1）与 orchestrator 调用（Step 4）一致；`PromptOrchestrator.build(brief, target_model, mode)` 与 composition 装配字段一致。

**未覆盖（按设计推迟）**：图生图真实调用 / `/images/edits`（紧随其后的独立一步，本计划只搭 EDIT 模式 prompt 接口）；C 阶段族×品类细分（后续）。

---

## 执行交接

计划已落盘 `docs/superpowers/plans/2026-05-29-category-style-profile.md`。两种执行方式：

1. **Inline Execution（本会话，推荐）** — 我在本会话按 executing-plans 逐任务实施（一品类/风格文件较碎，本会话连贯做更快），每个 Task 后可检查。
2. **Subagent-Driven** — 每 Task 派独立 subagent + 双段评审。

选哪种？
