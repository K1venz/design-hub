from dataclasses import dataclass, field

# 种子片段表：(field, value) -> 注入 prompt 的中文话术。正式文案由 image-prompt 出（ISSUE-0022）。
# 覆盖 ISSUE-0021 用户确认的首版下拉枚举全部取值，否则正常选项会 fail-fast 400。
_SEED_FRAGMENTS: dict[tuple[str, str], str] = {
    # 电商平台（4，收窄国内：去跨境亚马逊/Temu/TikTok→未登记 400，PRD §3.12.11）
    ("platform", "淘宝天猫1688"): "用于淘宝/天猫/1688 电商平台的商品展示图",
    ("platform", "拼多多"): "用于拼多多电商平台的商品展示图",
    ("platform", "京东"): "用于京东电商平台的商品展示图",
    ("platform", "抖音电商"): "用于抖音电商的商品展示图",
    # 国家地区（收窄：花生=中国方向，仅留中国；前端固定发 region=中国，PRD §3.12.12）
    ("region", "中国"): "商品面向中国市场",
    # 语言（收窄：仅中文/英文，默认中文，PRD §3.12.12）
    ("language", "中文"): "广告文字使用中文",
    ("language", "英文"): "广告文字使用英文",
}


@dataclass
class PromptModifierRegistry:
    """下拉值 → prompt 话术片段（可版本化、可测）。未知值 fail-fast。"""

    fragments: dict[tuple[str, str], str] = field(
        default_factory=lambda: dict(_SEED_FRAGMENTS)
    )

    def fragment(self, field_name: str, value: str) -> str:
        try:
            return self.fragments[(field_name, value)]
        except KeyError:
            raise ValueError(
                f"未知下拉值：{field_name}={value}（未在话术表登记）"
            ) from None


# FOOD 通用产品保真块（产品中性，#366 修「万物皆花生」）：逐字对齐
# image-prompt/category-cards/food/通用.md 的 ```text 块（行长 >100 故隐式拼接，勿改一字）。
# 单一事实源在卡、此处硬编码引用、三方核对 code 串==卡串；花生专属卡降级 backlog(food/peanut.md)。
_FOOD_FIDELITY = (
    "产品绝对保真：上传参考图里的产品（外形、结构、材质、配色、图案、品牌标识、包装上所有文字与排版）"
    "100% 原样保留——一个字、一个像素都不改、不重画、不翻译；"
    "只重绘产品周围的背景、衬托道具与光线。\n"
    "真实质感：严格按产品本身的真实材质表现质感（金属有金属光、塑料有塑料面、织物有布纹、"
    "食品有食品的自然光泽），不套用统一的假高光；表面真实、干爽、自然，"
    "严禁糖浆般高光/油亮反光/塑料假光泽与过度修图，保留材质本身的细微不均与真实细节。\n"
    "光与镜头：50mm f/2.8 近景浅景深，侧前方自然漫射光勾出产品的体积与凹凸、"
    "柔中带方向性硬阴影、与台面真实接触阴影；前景主体锐利、质感清晰。\n"
    "背景与道具：干净、得体、与产品调性相符的简洁背景与少量衬托道具，只为衬托产品、不喧宾夺主；"
    "严禁堆砌与产品无关的道具、食材或物件，不要无故出现与该产品无关的食物/植物/杂物。\n"
    "画面禁止：改动/重画/翻译产品本体与包装文字、塑料假高光、油亮反光、过度鲜艳饱和、"
    "堆砌与产品无关的道具/食材/物件、完美整齐的摆拍排列、人物/水印/多余文字。"
)

# 品类 → 保真块（PRD §3.12.11/12，MVP 只 FOOD 通用块；扩品类/产品级专属卡=加一条，YAGNI）。
_CATEGORY_CARDS: dict[str, str] = {
    "FOOD": _FOOD_FIDELITY,
}


@dataclass
class CategoryCardRegistry:
    """品类 → 保真块（PRD §3.12.11/12）。单一事实源=image-prompt 品类卡；未知品类 fail-fast。"""

    cards: dict[str, str] = field(default_factory=lambda: dict(_CATEGORY_CARDS))

    def card(self, category: str) -> str:
        try:
            return self.cards[category]
        except KeyError:
            raise ValueError(f"未知品类：{category}（未在品类卡表登记）") from None


# 图型卡物化块（套图，PRD §3.12.14）：逐字对齐 image-prompt/image-type-cards/<图型>.md
# 的 ```text 块。单一事实源在卡、此处硬编码引用、程序化核对 code 串==卡串（行长 >100 故
# 隐式拼接，勿改一字）。卖点有字版为模板：静态部分逐字核对，{overlay_texts} 槽运行时填充。
_TYPE_WHITE_BG = (
    "图型·白底主图：一张纯白无缝影棚背景上的产品电商主图照，真实商业摄影质感。"
    "产品居中摆放、占画面主体约八到九成、整体清晰锐利、细节完整可见；"
    "背景为纯净无杂色的纯白色，不放置任何道具与装饰。"
    "产品与台面之间保留真实的接触阴影与柔和的自然投影，"
    "光线均匀而有方向、产品轮廓边缘清晰不过曝——产品是真实摆放在白色背景纸上拍摄的，"
    "不是抠图悬浮贴上去的。"
)
_TYPE_SCENE = (
    "图型·场景图：一张产品置于真实生活使用场景中的摆拍照，自然光下的真实摄影质感。"
    "场景从该产品的实际使用环境中选取（居家、餐桌、厨房、办公等与产品用途相符的环境），"
    "环境叙事自然、有生活气息；产品仍是画面绝对主角、处于视觉焦点，"
    "场景与道具只做衬托、数量克制、且全部与产品的使用相关。"
    "画面中不出现人物与任何人体局部（包括手与手臂），不堆砌杂物。"
)
_TYPE_SELLING = (
    "图型·卖点特写：一张突出产品核心卖点的细节特写照，近景微距、真实商业摄影质感。"
    "镜头聚焦产品最具说服力的卖点部位（材质、工艺、成分、结构等细节），"
    "纹理清晰放大呈现、质感真实，构图留有适度干净的负空间。"
    "画面中不出现任何文字、标贴与水印。"
)
_TYPE_SELLING_TEXT_TPL = (
    "图型·卖点特写（带文案）：一张突出产品核心卖点的细节特写照，近景微距、真实商业摄影质感。"
    "镜头聚焦产品最具说服力的卖点部位，纹理清晰放大呈现、质感真实，"
    "构图在画面上方或一侧留出干净的负空间用于排版文案。\n"
    "图上文案，逐字呈现、一字不增不减不改、不翻译：{overlay_texts}。"
    "文案以简洁现代的无衬线字体排版，字色与底色对比清晰、位置不遮挡产品主体；"
    "除上述文案外，画面中不出现任何其他文字、标贴与水印。"
)

IMAGE_TYPES = ("白底", "场景", "卖点")  # 中文枚举 key（#486 终裁），与卡文件名/前端/SSE 一字串


@dataclass
class ImageTypeRegistry:
    """图型 → 物化块（PRD §3.12.14）。单一事实源=image-prompt 图型卡；未知图型 fail-fast。

    卖点按有无 overlay_texts 选块：缺省=无字特写；有=模板按卡内格式（全角引号顿号）填充。
    """

    def block(self, image_type: str, overlay_texts: tuple[str, ...] = ()) -> str:
        if image_type == "白底":
            return _TYPE_WHITE_BG
        if image_type == "场景":
            return _TYPE_SCENE
        if image_type == "卖点":
            if not overlay_texts:
                return _TYPE_SELLING
            joined = "、".join(f"「{t}」" for t in overlay_texts)
            return _TYPE_SELLING_TEXT_TPL.format(overlay_texts=joined)
        raise ValueError(f"未知图型：{image_type}（未在图型卡表登记）")


# 复刻模式物化块（爆款复刻 PRD §3.13）：逐字对齐 image-prompt/clone-mode-cards/复刻.md
# 的 ```text 块。两档纯静态零槽位（产品图==1 已锁，角色指认句依赖「产品前·参考后」保序契约）。
_CLONE_REF_STYLE = (
    "复刻·参考风格：本次有两类参考图——第 1 张为用户产品图，产品保真以它为准；"
    "其余为爆款风格参考图，仅用于学习其整体风格调性、色彩氛围、光影感觉与构图思路，"
    "按这种风格为该产品重新设计一个合适的场景。"
    "风格参考图中的产品、品牌标识与所有文字一律不出现在画面中；"
    "画面中的产品只能是用户产品图中的那个产品，其外形、包装与文字原样保留、不被风格参考图带偏。"
)
_CLONE_FULL = (
    "复刻·高度复刻：本次有两类参考图——第 1 张为用户产品图，产品保真以它为准；"
    "其余为爆款版式参考图，请照搬其视觉结构：布局、机位、景别、道具位置关系与画面节奏，"
    "把版式参考图中产品所在的位置替换为用户产品图中的那个产品（占位、比例与视角对应），"
    "场景细节允许略有差异。版式参考图中的原产品、品牌标识与营销文案一律不出现在画面中；"
    "用户产品的外形、包装与文字 100% 原样保留、一字不改，绝不被版式参考图中的产品样式带偏。"
    "若下方用户要求中明确给出图上文案，仅以引号内原文逐字呈现；否则画面中不出现任何营销文字。"
)

CLONE_MODES = ("参考风格", "高度复刻")  # 中文档位 key（同图型卡先例）


@dataclass
class CloneModeRegistry:
    """复刻档位 → 物化块（PRD §3.13）。单一事实源=image-prompt 复刻卡；未知档位 fail-fast。"""

    def block(self, clone_mode: str) -> str:
        if clone_mode == "参考风格":
            return _CLONE_REF_STYLE
        if clone_mode == "高度复刻":
            return _CLONE_FULL
        raise ValueError(f"未知复刻档位：{clone_mode}（合法：{'/'.join(CLONE_MODES)}）")


# 编辑模式物化块（二次编辑 PRD §3.12.13 / ISSUE-0040）：逐字对齐
# image-prompt/edit-mode-cards/编辑.md 的 ```text 块。两档纯静态零槽位；喂序契约：
# 第 1 张=被编辑源图（基底）、其后 1..3 张=迭代链根原始产品图（保真锚，D2 防累积失真）。
_EDIT_DELTA = (
    "编辑·微调：本次是对已生成图的定向微调。第 1 张为当前画面（被编辑基底）——构图、场景、光线、"
    "配色与一切未被下方修改要求点名的元素全部保持与它一致，不重新设计；"
    "其后的图为产品原图——画面中产品的外形、包装与所有文字以产品原图为准逐字逐细节保留、"
    "一个字一个像素都不改，不被当前画面中产品的任何失真带偏。"
    "仅按下方修改要求做最小幅度的定向调整，修改要求未提到的一概不动。"
)
_EDIT_FULL = (
    "编辑·重做：本次基于已生成图重新创作。第 1 张为此前画面（仅作方向参考，不必沿用其构图）；"
    "其后的图为产品原图——画面中的产品只能是产品原图中的那个产品，"
    "其外形、包装与所有文字以产品原图为准 100% 原样保留、不改一字。"
    "请按下方新要求重新设计场景、构图与光线：画面如真实相机拍摄、自然光影、"
    "产品与台面有真实接触阴影，不堆砌与产品无关的道具，不出现水印与多余文字。"
)

EDIT_MODES = ("delta", "full")  # registry key = edit_mode 列值（英文 key 对齐 DB 枚举，第六类卡）


@dataclass
class EditModeRegistry:
    """编辑档位 → 物化块（PRD §3.12.13/ISSUE-0040）。

    单一事实源=image-prompt 编辑卡；未知档位 fail-fast。
    """

    def block(self, edit_mode: str) -> str:
        if edit_mode == "delta":
            return _EDIT_DELTA
        if edit_mode == "full":
            return _EDIT_FULL
        raise ValueError(f"未知编辑档位：{edit_mode}（合法：{'/'.join(EDIT_MODES)}）")


def compose_edit_prompt(
    prompt: str,
    modifiers: dict[str, str],
    registry: PromptModifierRegistry,
    *,
    edit_registry: EditModeRegistry,
    edit_mode: str,
) -> str:
    """编辑 final prompt = 编辑档位块（自含产品保真） → 用户编辑指令（必填） → modifier 片段。

    不注入品类保真块（其「只重绘周围」与 delta 锚定冲突，#645）、图型卡、父 prompt（Q-β：
    源图即父 prompt 执行结果，文本二传必与本轮指令打架）。指令必填（E-⑤，路由层 422
    先挡，此处兜底 fail-fast）。未知档位/下拉值均 fail-fast。
    """
    base = prompt.strip()
    if not base:
        raise ValueError("编辑指令不能为空")
    edit_block = edit_registry.block(edit_mode)
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    body = base if not fragments else base + "。" + "；".join(fragments)
    return edit_block + "\n" + body


def compose_clone_prompt(
    prompt: str,
    modifiers: dict[str, str],
    registry: PromptModifierRegistry,
    *,
    category: str,
    card_registry: CategoryCardRegistry,
    clone_registry: CloneModeRegistry,
    clone_mode: str,
) -> str:
    """复刻 final prompt = 保真块 → 复刻档位块(含角色指认) → 用户统一要求(选填) → modifier 片段。

    与 compose_prompt 的差异：用户文本**可为空**（模板图+产品图已承载语义，PRD §3.13 选填）；
    不叠图型卡（模板已决定构图）。未知档位/品类/下拉值均 fail-fast。
    """
    fidelity = card_registry.card(category)
    clone_block = clone_registry.block(clone_mode)
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    base = prompt.strip()
    parts = [fidelity, clone_block]
    if base and fragments:
        parts.append(base + "。" + "；".join(fragments))
    elif base:
        parts.append(base)
    elif fragments:
        parts.append("；".join(fragments))
    return "\n".join(parts)


def compose_prompt(
    prompt: str,
    modifiers: dict[str, str],
    registry: PromptModifierRegistry,
    *,
    category: str,
    card_registry: CategoryCardRegistry,
    image_type_block: str | None = None,
) -> str:
    """最终 prompt = 品类保真块 [+ 图型卡块] + 用户自由文本 + 各 modifier 片段。

    保真块按 category 选（PRD §3.12.11），拼在最前（QA #196/#198 验过位置）；
    图型卡块仅套图 plan 路径注入（PRD §3.12.14，单图流不带、维持现状零破坏）；
    未知品类 / 未知下拉值均 fail-fast。
    """
    base = prompt.strip()
    if not base:
        raise ValueError("prompt 不能为空")
    fidelity = card_registry.card(category)
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    body = base if not fragments else base + "。" + "；".join(fragments)
    if image_type_block is None:
        return fidelity + "\n" + body
    return fidelity + "\n" + image_type_block + "\n" + body
