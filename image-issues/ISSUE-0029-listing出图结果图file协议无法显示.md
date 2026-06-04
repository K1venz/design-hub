---
id: ISSUE-0029
title: listing 出图结果图无法显示——前端直塞 file:// 到 <img>，浏览器禁止加载本地资源（线上也坏）
status: 待确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 出图成功但结果完全看不到；listing 核心交付不可用，且线上必坏
reporter: QA
owner: 前端           # 立即修(dev rewrite)归前端；上线前的后端 HTTP 图床归开发（见方案B）
created: 2026-06-04
related:
  - 前端: image-web/src/components/listing/ResultGallery.tsx:65（`<img src={s.url}>` 直接用 file://）
  - 前端: image-web/vite.config.ts（dev `/__localimg?p=` 图床中间件已存在，ResultGallery 未用）
  - code: image-code/src/design_hub/infrastructure/storage/local_image.py（出图落 file://）
  - issue: ISSUE-0016（缺静态图床，本条是其在 listing 结果区的具体爆发）
---

## 现象
listing「商品套图」点出图 → **出图成功**（`POST /api/listing/generate`→200、SSE→200、真图已落
`image-code/generated/<id>.png`），但结果区**裂图、显示不出来**。

## 根因（QA 实测 + 读码定位，Playwright 复现）
- SSE `image_generated` 事件给的 url = `file:///…/generated/<id>.png`（后端 `LocalImageStore` 落本地）。
- 前端 `ResultGallery.tsx:65` 直接 `<img src={s.url}>` 用了这个 `file://`。
- 浏览器**禁止网页加载本地 file:// 资源** → console：`Not allowed to load local resource: file:///…png`，network `[FAILED]`。
- 对照：上传预览用 `blob:`（OK）；项目候选图走了 dev 图床（OK）；**唯独 listing 结果区没改写**。
- ⚠️ **线上（203.0.113.10）同样坏且更严重**：prod 无 `/__localimg`，file:// 在任何浏览器都加载不了 → listing 结果永远裂图。

## 复现
1. 登录 → 商品套图 → 上传产品图 → 写卖点 → 开始出图 → 等出图完成。
2. 结果区裂图；devtools console 见 `Not allowed to load local resource: file://…`。

## 修复方案（两步，建议都做）
**A. 立即修（解 dev 眼前，前端，~0.5h）**：`ResultGallery` 渲染前把 `file://<abs>` 改写成
   `/__localimg?p=<encodeURIComponent(abs)>`（dev 图床已存在，QA 实测 `GET /__localimg?p=…`→**200 image/png**）。
   立刻能在 dev 看到出图。**仅 dev 有效**。
**B. 上线前必做（正解，后端，~0.5–1 人天）**：后端加 HTTP 图床端点（服务 `generated/`，如
   `GET /images/{name}` 或 `/generated/{name}`，参照已有 `GET /uploads/{id}` 鉴权与代理模式），
   出图结果/SSE 返回该 **http 路径**而非 `file://`；前端改用该 url（dev 的 /__localimg 可退役）。
   这才让 **prod listing 结果可显示**，并彻底收口 ISSUE-0016。

## 排期建议（QA 视角，PM 定）
- **P1**：A 先合（前端，今天就能让 dev 看到图）；B 列入 listing 上线前必做项（后端，与 ISSUE-0016 合并做）。
- 不修 B → listing 在生产环境完全不可用（出了图但用户永远看不到）。

## 处理记录
- 2026-06-04 [QA] 本地整栈 + Playwright 复现：出图成功但结果区裂图，定位 ResultGallery 直塞 file://；
  dev 图床 /__localimg 实测可取图(200)。P1 开单，A 前端立即修 / B 后端上线前必做。owner=前端（B 转开发）。
