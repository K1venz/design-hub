# listing base(gpt-image-2) 花生样张 · 共评素材（QA 初判）

- 出图：server qa 实例，模型 = **gpt-image-2 (base)**，源图 = 花生精修，n=1，TOS qa-generate 桶。
- 用途：用户 + PM 5 维共评（产品保真 / 文案 / 风格 / 场景 / 可用），定 listing 上线档位（base vs vip）。
- ⚠️ 本地双击 PNG 看（签名 url 已 TTL=10 过期，看文件不看 url）。
- 出图时延（F2 佐证）：8 张 happy 单张 100–155s；A4 n=7 单次调用 190.7s；**F2 P95 = 193s ≤ 5min PASS**。

## 逐张（QA 初判，PM 做权威逐字文案核 #149）

| # | 文件 | 平台 | 比例 | 语言 | 品牌(AI自拟) | 文案要点 | QA 可用判定 |
|---|---|---|---|---|---|---|---|
| 1 | 亚马逊-1x1-英文.png | 亚马逊 | 1:1 | 英文 | ROASTED PEANUTS | Natural Ingredients / Rich in Protein / Great Taste & Crunch / 66G | ✅ 可用。英文无拼写错；`PURPLE-COATED` 是「七彩/花青素」的生硬英译（非错） |
| 2 | 淘宝天猫1688-3x4-中文.png | 淘宝天猫1688 | 3:4 | 中文 | 嘴嘴熊 | 颗粒饱满 香脆可口 / 高山种植·自然晾晒·原味轻盐 / 富含花青素 / 非油炸工艺 | ✅ 可用。中文**全对、无乱码错别字** |
| 3 | TikTok_Shop-9x16-英文.png | TikTok Shop | 9:16 | 英文 | KIKI BEAR | Premium Peanuts / Crispy, Nutty & Irresistible / No Artificial Additives | ✅ 可用。英文无错；`GAO SHAN`(高山拼音) 可接受 |
| 4 | Temu-16x9-英文.png | Temu | 16:9 | 英文 | FLOWER PEANUTS | Sweet·Crispy·Naturally Delicious / Rich in Protein | ✅ 可用。英文无错；`Flower Peanuts`(花生生硬直译) 怪但可作品牌名 |
| 5 | 拼多多-1x1-中文.png | 拼多多 | 1:1 | 中文 | 嘴嘴熊 | 颗粒饱满 香脆可口 / 七彩花生·自然原香 / 富含花青素 / 颗颗精选·轻烘慢烤 | ✅ 可用。中文**全对** |
| 6 | 京东-3x4-中文.png | 京东 | 3:4 | 中文 | 嘴嘴熊 | 颗颗饱满 香脆可口 / 高山种植·自然晾晒·原香原味 / 富含花青素 | ✅ 可用。中文**全对** |
| 7 | 抖音电商-9x16-中文.png | 抖音电商 | 9:16 | 中文 | 嘴嘴熊 | 颗颗饱满·香脆可口 / 粒大易剥 / 新鲜炒制 / 香脆美味 不添加防腐剂 / 酥香可口 好吃不停 | ✅ 可用。中文**全对** |
| 8 | 亚马逊-16x9-英文.png | 亚马逊 | 16:9 | 英文 | Peanuts | Rich·Natural·Delicious / High Mountain Grown / Net Wt 66g(2.33oz) | 🟡 待 PM 核：大标题疑似 **`PRENIUM`→应为 `PREMIUM`**（AI 文字疑似 typo）；oz 单位换算✅ |

## QA 初判汇总（5 维）

- **① 产品保真**：8/8 OK。花生本体真实；紫色颗粒 = **七彩花生/富含花青素**（中文样张明确标注），是真实产品概念、非幻觉，跨样张一致。
- **② 文案正确**：**4 张中文全对、无乱码无错别字**（AI 直出中文重灾区却很干净，超预期）；4 张英文 3 张全对，**仅样张 8 大标题疑似 `PRENIUM` typo 待 PM 逐字核**。小角标装饰字（如 `SATISFYING SNACK`/`100% DELICIOUS`）个别轻微变形，属装饰非主文案。
- **③ 风格一致**：8/8 OK。kawaii 熊吉祥物 + 暖纸底 + 电商 listing 版式，符合各平台调性。品牌名各样张不同（嘴嘴熊/KIKI BEAR/FLOWER PEANUTS…）= prompt 未固定品牌所致，正式上线由用户锁定品牌即可，非缺陷。
- **④ 场景合理**：8/8 OK。木桌 + 散花生 + 碗装，突出产品、不违和。
- **⑤ 可用判定**：**初判 7/8 可直接用、1/8(样张8) 待 PM 确认 `PRENIUM` 是否 typo**（若是则该张返工/调 prompt）。→ **QA 初判可用率 ≈ 7-8/8 = 87.5-100%**，远超 PRD §3.12.6 的 50-60% 口径。

> 权威文案逐字核归 PM（#149）；本表为 QA 初判，两份并陈供用户拍。
