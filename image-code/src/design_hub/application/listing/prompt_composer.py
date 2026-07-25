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
            raise ValueError(f"暂不支持的选项：{value}") from None


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

# 4 新品类保真块（ISSUE-0060，注册表制）：逐字对齐 image-prompt/category-cards/<cat>/通用.md
# 的 ```text 块（卡稿 de9219f，草案·prompt 权威后补复核）；卡↔code 逐字 pytest 闸自动核对。
_FASHION_FIDELITY = (
    "产品绝对保真：上传参考图里的服装（版型廓形、面料材质、色彩、图案印花、绣花、缝线"
    "细节、吊牌/领标/洗标上所有文字）100% 原样保留——一个字、一个像素都不改、"
    "不重画、不翻译；只重绘服装周围的背景与衬托光线。\n"
    "面料与版型：严格还原面料真实质感（棉布有棉纹、丝绸有受控光泽起伏而不过曝、羊绒有"
    "绒毛感），版型廓形精确保留；面料色彩忠实原色——不提亮、不改饱和度；图案/印花/"
    "绣花位置与比例不偏移；服装自然垂坠，保留合理褶皱与垂感，严禁熨烫绷平感。\n"
    "光与镜头：50mm f/2.8–f/4，侧前方自然漫射光勾出面料质感与立体感，柔"
    "中带方向性硬阴影；平铺俯视 30–45° 或衣架侧挂；前景服装锐利，面料纹路清晰"
    "可见。\n"
    "背景与道具：与服装调性相符的干净简洁背景；道具克制，全部与服装使用场景相关，不堆"
    "叠无关物件。\n"
    "画面禁止：改动面料色彩/版型廓形/图案印花/绣花/吊牌文字、面料异常反光与塑料假"
    "光泽、出现任何人物与人体局部（含手与手臂）、水印/多余文字、完美无折叠感的过度熨"
    "烫摆放。"
)

_BEAUTY_FIDELITY = (
    "产品绝对保真：上传参考图里的美妆产品（瓶身外形、材质、色号/内容物颜色、品牌标识"
    "与标签上所有文字）100% 原样保留——一个字、一个像素都不改、不重画、不翻译；"
    "只重绘产品周围的背景、道具与光线。\n"
    "材质与色号：玻璃/亚克力折射高光为小亮点或高光线，而非大白块；高光面积控制在瓶身"
    "极小范围，品牌文字在高光区保持可读；金属泵头/盖帽呈细腻金属反射感，不是塑料质感"
    "；色号/内容物颜色忠实原色——不提亮、不改深浅；哑光膏体呈柔和漫散射，无油亮感。\n"
    "光与镜头：50mm–85mm f/2.8–f/4，侧前方 45° 自然漫射光防正"
    "面玻璃过曝，柔中带方向性硬阴影，与台面真实接触阴影；前景产品锐利，瓶身形态与质感"
    "清晰。\n"
    "背景与道具：白色大理石/米白棉布/浅调原木等简洁台面，道具极度克制且与产品品类相"
    "关，严禁堆砌无关美妆产品与杂物。\n"
    "画面禁止：玻璃大白块高光/镜面过曝、色号改色/提亮/失真、金属泵头塑料感、瓶身棱"
    "角磨平、改动/重画品牌文字（含高光区消失）、堆砌无关产品、人物/水印/多余文字。"
)

_SHOES_FIDELITY = (
    "产品绝对保真：上传参考图里的鞋（鞋型廓形、鞋面材质、配色、鞋底橡胶纹路、品牌 L"
    "OGO/刺绣/贴标及所有文字）100% 原样保留——一个字、一个像素都不改、不重"
    "画、不翻译；只重绘鞋周围的背景、台面与光线。\n"
    "鞋型与材质：鞋尖形状、鞋跟高度、鞋帮轮廓精确保留；皮革有自然折纹与受控方向性高光"
    "（非镜面/塑料光泽）；织物网面纹理清晰可见，不过度平滑；鞋底橡胶接地纹路与微凸结"
    "构完整保留；五金配件（鞋钩/铆钉/金属扣）呈真实金属质感；成对展示时左右脚对称正"
    "确、方向相反。\n"
    "光与镜头：50mm f/2.8–f/4，侧 45° 机位，侧前方自然漫射光，皮革"
    "面有定向高光但面积克制，柔中带真实接触阴影；前景主体锐利，材质纹理清晰。\n"
    "背景与道具：简洁干净台面（白底/木板/大理石），道具克制不超 1–2 件且全部与"
    "鞋品使用相关，不堆砌无关物件。\n"
    "画面禁止：鞋型廓形改变（鞋尖/鞋跟/鞋帮轮廓失真）、皮革塑料光泽、鞋底纹路消失/"
    "平滑化、品牌 LOGO 替换/变形、成对展示左右同向、人物/水印/多余文字。"
)

_DIGITAL_FIDELITY = (
    "产品绝对保真：上传参考图里的数码产品（设备外形、材质、配色、接口类型与位置、按钮"
    "布局、摄像头模组数量与形状、品牌 LOGO 及所有文字）100% 原样保留——一"
    "个字、一个像素都不改、不重画、不翻译；只重绘产品周围的背景、台面与光线。\n"
    "材质与屏幕：金属铝合金表面有拉丝质感与细腻方向性反光（细长亮线/小亮点），不要镜"
    "面铺满整面（产品变\"镜子\"）；玻璃背板折射克制可见；接口金属针脚与设备缝隙细节忠"
    "实还原；屏幕内容按 brief 指定（熄屏/纯色留白/指定内容），不自行渲染任何"
    " UI 界面、图标、图片或文字。\n"
    "光与镜头：50mm f/2.8–f/4，侧前方自然光，金属面高光克制（小面积方向"
    "性亮点），防整面过曝；前景设备锐利，材质细节与接缝层次清晰；与台面真实接触阴影。\n"
    "背景与道具：简洁深色/浅色台面，道具克制且与产品品类相关，不堆砌无关数码产品或杂"
    "物。\n"
    "画面禁止：屏幕自行生成 UI/图标/文字、金属镜面过曝（整面白光）、接口类型/数"
    "量/位置篡改、摄像头模组简化或遗漏、品牌 LOGO 替换/变形、过度科技光效（激"
    "光/扫光束/强制光晕）、人物/水印/多余文字。"
)

# 品类 → 保真块（PRD §3.12.11/12）：FOOD + 4 新品类（注册表制，加品类=加卡+注册，不动架构）。
_CATEGORY_CARDS: dict[str, str] = {
    "FOOD": _FOOD_FIDELITY,
    "FASHION": _FASHION_FIDELITY,
    "BEAUTY": _BEAUTY_FIDELITY,
    "SHOES": _SHOES_FIDELITY,
    "DIGITAL": _DIGITAL_FIDELITY,
}


@dataclass
class CategoryCardRegistry:
    """品类 → 保真块（PRD §3.12.11/12）。单一事实源=image-prompt 品类卡；未知品类 fail-fast。"""

    cards: dict[str, str] = field(default_factory=lambda: dict(_CATEGORY_CARDS))

    def card(self, category: str) -> str:
        try:
            return self.cards[category]
        except KeyError:
            raise ValueError(f"未知品类：{category}") from None


_BASE_REFERENCE_FIDELITY = (
    "参考图是画面主体的唯一事实来源：保持主体结构、轮廓比例、颜色、材质、已有 Logo 与文字不变，"
    "不替换、不翻译、不凭空增删主体内容；只按照用户明确要求调整构图、背景、光线与整体视觉呈现。"
)


def resolve_fidelity_prompt(
    category: str | None, registry: CategoryCardRegistry
) -> str:
    """无品类使用基础保真；显式品类在基础保真后叠加专项约束。"""
    if category is None:
        return _BASE_REFERENCE_FIDELITY
    return _BASE_REFERENCE_FIDELITY + "\n" + registry.card(category)


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
WHITE_BG_TYPE = "白底"  # 平台合规纯白主图：剥离用户自由文本防强场景污染（ISSUE-0052 档A）


@dataclass
class ImageTypeRegistry:
    """图型 → 物化块（PRD §3.12.14）。单一事实源=image-prompt 图型卡；未知图型 fail-fast。

    卖点按有无 overlay_texts 选块：缺省=无字特写；有=模板按卡内格式（全角引号顿号）填充。
    """

    def drops_user_styling(self, image_type: str) -> bool:
        """该图型是否剥离用户自由文本（ISSUE-0052 档A）。

        白底主图=纯白无缝影棚背景的平台合规主图，用户强场景描述会压过纯白背景 →
        组装时不注入用户自由文本（仍保保真块+白底卡块+modifiers）。场景/卖点保留用户文本。
        """
        return image_type == WHITE_BG_TYPE

    def block(self, image_type: str, overlay_texts: tuple[str, ...] = ()) -> str:
        if image_type == WHITE_BG_TYPE:
            return _TYPE_WHITE_BG
        if image_type == "场景":
            return _TYPE_SCENE
        if image_type == "卖点":
            if not overlay_texts:
                return _TYPE_SELLING
            joined = "、".join(f"「{t}」" for t in overlay_texts)
            return _TYPE_SELLING_TEXT_TPL.format(overlay_texts=joined)
        raise ValueError(f"未知图型：{image_type}")


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
    "复刻·完全复刻：本次有两类参考图——第 1 张为用户产品图，"
    "产品保真以它为准；其余为爆款参考图，请最大程度完整复制其画面风格："
    "构图、机位、景别、光影、配色、背景与版式节奏都照参考图来，"
    "把参考图中产品所在的位置替换为用户产品图中的那个产品（占位、"
    "比例与视角对应）。参考图中的原产品、品牌标识与所有文字（大标题、"
    "卖点角标、banner 等）一律不出现在画面中，"
    "画面中不出现任何营销文字、标贴与水印，也不要自行编造任何文案。"
    "用户产品的外形、包装与文字 100% 原样保留、一字不改，"
    "绝不被参考图中的产品样式带偏。"
)

CLONE_MODES = ("参考风格", "完全复刻")  # 中文档位 key（同图型卡先例，ISSUE-0062 改版）


@dataclass
class CloneModeRegistry:
    """复刻档位 → 物化块（PRD §3.13）。单一事实源=image-prompt 复刻卡；未知档位 fail-fast。"""

    def block(self, clone_mode: str) -> str:
        if clone_mode == "参考风格":
            return _CLONE_REF_STYLE
        if clone_mode == "完全复刻":
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
    category: str | None,
    card_registry: CategoryCardRegistry,
    clone_registry: CloneModeRegistry,
    clone_mode: str,
) -> str:
    """复刻 final prompt = 保真块 → 复刻档位块(含角色指认) → 用户统一要求(选填) → modifier 片段。

    与 compose_prompt 的差异：用户文本**可为空**（模板图+产品图已承载语义，PRD §3.13 选填）；
    不叠图型卡（模板已决定构图）。未知档位/品类/下拉值均 fail-fast。
    """
    fidelity = resolve_fidelity_prompt(category, card_registry)
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
    category: str | None,
    card_registry: CategoryCardRegistry,
    image_type_block: str | None = None,
    drop_user_text: bool = False,
) -> str:
    """最终 prompt = 品类保真块 [+ 图型卡块] + 用户自由文本 + 各 modifier 片段。

    保真块按 category 选（PRD §3.12.11），拼在最前（QA #196/#198 验过位置）；
    图型卡块仅套图 plan 路径注入（PRD §3.12.14，单图流不带、维持现状零破坏）；
    未知品类 / 未知下拉值均 fail-fast。

    drop_user_text（ISSUE-0052 档A，白底图）：剥离用户自由文本，防强场景描述压过纯白背景 →
    仅保真块 + 白底卡块 + modifiers。用户文本仍必填（供场景/卖点），此处只是不注入白底图。
    """
    base = prompt.strip()
    if not base:
        raise ValueError("请先描述想要的画面（风格、场景等）")
    fidelity = resolve_fidelity_prompt(category, card_registry)
    fragments = [registry.fragment(k, v) for k, v in modifiers.items()]
    mods = "；".join(fragments)
    if drop_user_text:
        parts = [fidelity]
        if image_type_block is not None:
            parts.append(image_type_block)
        if mods:
            parts.append(mods)
        return "\n".join(parts)
    body = base if not mods else base + "。" + mods
    if image_type_block is None:
        return fidelity + "\n" + body
    return fidelity + "\n" + image_type_block + "\n" + body
