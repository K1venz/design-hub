"""公开首页「成果展示区」精选清单（人工质检后打进代码库）。

素材=prod 真实套图产出，经人工逐张质检精选，server-side copy 到 generate 桶
`showcase/` 前缀（编号即展示顺序）。桶保持私有：GET /showcase 对每项现签
预签名 url（TTL 同 tos_signed_url_ttl），无鉴权、无用户数据。
换素材 = 改本清单 + 传新对象，无需迁移/建表。

配方（ISSUE-0053「做同款」）：每项附 `recipe`——**可复用输入**（图型配比/比例/
风格描述=job.prompt/平台·语言等 modifiers/品类），对齐 ListingGenerateRequest 套图
字段，供前端「做同款」预填 /set。**绝不含组装后的内部卡 prompt**（没存·核心资产
不外泄·展示了也复用不了）；亦不含 overlay_texts（裁决 (a)：文案自己写）与 uploads
（配方≠素材，产品图必须用户自传）。值从 07-02 五单真实套图 job 只读回填、写死进本清单。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Recipe:
    """做同款可复用套图配方（对齐 ListingGenerateRequest 套图字段的可复用子集）。

    只含用户可复用输入；无内部卡 prompt、无 overlay_texts、无 uploads（ISSUE-0053 口径）。
    """

    category: str  # 保真卡品类（FOOD）；预填选对应品类保真卡
    ratio: str  # 比例（1:1/9:16/16:9/3:4）
    plan: dict[str, int]  # 图型配比：白底/场景/卖点 → 张数（Σ=张数）
    styling: str  # 风格描述 = 用户自由文本（listing_job.prompt）
    modifiers: dict[str, str]  # region/language/platform（对齐请求 modifiers）


# ── 5 单真实套图配方（07-02 showcase 批次、admin 名下，prod 只读回填）──
# 每单套图配比统一 白底1+场景2+卖点2（n=5）；平台/比例/风格描述来自真实 job。

_RECIPE_PEANUT_TAOBAO = Recipe(
    category="FOOD",
    ratio="1:1",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling="暖调原木餐桌与米色麻布衬底，散落几粒带壳花生点缀，柔和自然晨光，温馨休闲零食氛围，画面干净高级",
    modifiers={"region": "中国", "language": "中文", "platform": "淘宝天猫1688"},
)
_RECIPE_PEANUT_DOUYIN = Recipe(
    category="FOOD",
    ratio="9:16",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling="高山田园清新风，远处青山与蓝天，竹匾晾晒花生的自然场景，通透明亮的阳光，竖版构图上方留白",
    modifiers={"region": "中国", "language": "中文", "platform": "抖音电商"},
)
_RECIPE_PEANUT_JD_EN = Recipe(
    category="FOOD",
    ratio="16:9",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling=(
        "现代简约横幅构图，浅奶油色背景大面积留白，产品居于一侧，"
        "另一侧散放花生粒与木勺，柔和棚拍光，高端电商 banner 质感"
    ),
    modifiers={"region": "中国", "language": "英文", "platform": "京东"},
)
_RECIPE_THROAT_JD = Recipe(
    category="FOOD",
    ratio="3:4",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling="清爽洁净的白色大理石台面，蓝黄品牌色呼应的背景，点缀薄荷叶与蜂蜜元素，通透明亮光线，药房级洁净质感",
    modifiers={"region": "中国", "language": "中文", "platform": "京东"},
)
_RECIPE_THROAT_PDD = Recipe(
    category="FOOD",
    ratio="1:1",
    plan={"白底": 1, "场景": 2, "卖点": 2},
    styling="明亮居家窗边场景，浅色木质托盘上摆放产品，旁边一杯温水与几颗润喉糖，清晨柔光，清新治愈氛围",
    modifiers={"region": "中国", "language": "中文", "platform": "拼多多"},
)


@dataclass(frozen=True)
class ShowcaseEntry:
    key: str  # generate 桶对象 key（showcase/NN.png，NN=展示顺序）
    image_type: str  # 白底 | 场景 | 卖点
    caption: str  # 首页一句话说明
    recipe: Recipe  # 做同款可复用配方（同套图的多张精选共享一份）


# 2026-07-02 首批：5 套 prod 套图（花生×3 / 润喉糖×2，25 张）人工精选 13 张。
# recipe 归属由「品类×图型/比例」确定映射（花生 1:1淘宝/9:16抖音/16:9英文京东；
# 润喉糖 3:4京东/1:1拼多多），与 job 风格描述逐条印证。
SHOWCASE_ENTRIES: tuple[ShowcaseEntry, ...] = (
    ShowcaseEntry("showcase/01.png", "白底", "花生·白底主图", _RECIPE_PEANUT_TAOBAO),
    ShowcaseEntry("showcase/02.png", "场景", "花生·高山晾晒场景", _RECIPE_PEANUT_DOUYIN),
    ShowcaseEntry("showcase/03.png", "卖点", "润喉糖·图上文案卖点", _RECIPE_THROAT_JD),
    ShowcaseEntry("showcase/04.png", "场景", "花生·英文营销横幅", _RECIPE_PEANUT_JD_EN),
    ShowcaseEntry("showcase/05.png", "卖点", "花生·图上文案卖点", _RECIPE_PEANUT_TAOBAO),
    ShowcaseEntry("showcase/06.png", "场景", "润喉糖·清晨窗边场景", _RECIPE_THROAT_PDD),
    ShowcaseEntry("showcase/07.png", "卖点", "花生·自然晾晒卖点", _RECIPE_PEANUT_DOUYIN),
    ShowcaseEntry("showcase/08.png", "场景", "润喉糖·品牌色场景", _RECIPE_THROAT_JD),
    ShowcaseEntry("showcase/09.png", "卖点", "花生·英文卖点特写", _RECIPE_PEANUT_JD_EN),
    ShowcaseEntry("showcase/10.png", "场景", "花生·暖木餐桌场景", _RECIPE_PEANUT_TAOBAO),
    ShowcaseEntry("showcase/11.png", "卖点", "润喉糖·图上文案卖点", _RECIPE_THROAT_PDD),
    ShowcaseEntry("showcase/12.png", "场景", "花生·高山竹匾场景", _RECIPE_PEANUT_DOUYIN),
    ShowcaseEntry("showcase/13.png", "卖点", "润喉糖·蜂蜜暖调卖点", _RECIPE_THROAT_JD),
)
