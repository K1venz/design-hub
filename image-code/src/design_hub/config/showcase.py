"""公开首页「成果展示区」精选清单（人工质检后打进代码库）。

素材=prod 真实套图产出，经人工逐张质检精选，server-side copy 到 generate 桶
`showcase/` 前缀（编号即展示顺序）。桶保持私有：GET /showcase 对每项现签
预签名 url（TTL 同 tos_signed_url_ttl），无鉴权、无用户数据、不泄漏 prompt。
换素材 = 改本清单 + 传新对象，无需迁移/建表。
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ShowcaseEntry:
    key: str  # generate 桶对象 key（showcase/NN.png，NN=展示顺序）
    image_type: str  # 白底 | 场景 | 卖点
    caption: str  # 首页一句话说明


# 2026-07-02 首批：5 套 prod 套图（花生×3 / 润喉糖×2，25 张）人工精选 13 张。
SHOWCASE_ENTRIES: tuple[ShowcaseEntry, ...] = (
    ShowcaseEntry(key="showcase/01.png", image_type="白底", caption="花生·白底主图"),
    ShowcaseEntry(key="showcase/02.png", image_type="场景", caption="花生·高山晾晒场景"),
    ShowcaseEntry(key="showcase/03.png", image_type="卖点", caption="润喉糖·图上文案卖点"),
    ShowcaseEntry(key="showcase/04.png", image_type="场景", caption="花生·英文营销横幅"),
    ShowcaseEntry(key="showcase/05.png", image_type="卖点", caption="花生·图上文案卖点"),
    ShowcaseEntry(key="showcase/06.png", image_type="场景", caption="润喉糖·清晨窗边场景"),
    ShowcaseEntry(key="showcase/07.png", image_type="卖点", caption="花生·自然晾晒卖点"),
    ShowcaseEntry(key="showcase/08.png", image_type="场景", caption="润喉糖·品牌色场景"),
    ShowcaseEntry(key="showcase/09.png", image_type="卖点", caption="花生·英文卖点特写"),
    ShowcaseEntry(key="showcase/10.png", image_type="场景", caption="花生·暖木餐桌场景"),
    ShowcaseEntry(key="showcase/11.png", image_type="卖点", caption="润喉糖·图上文案卖点"),
    ShowcaseEntry(key="showcase/12.png", image_type="场景", caption="花生·高山竹匾场景"),
    ShowcaseEntry(key="showcase/13.png", image_type="卖点", caption="润喉糖·蜂蜜暖调卖点"),
)
