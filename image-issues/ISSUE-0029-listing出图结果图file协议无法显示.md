---
id: ISSUE-0029
title: listing 出图结果图无法显示——前端直塞 file:// 到 <img>，浏览器禁止加载本地资源（线上也坏）
status: 修复中        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 出图成功但结果完全看不到；listing 核心交付不可用，且线上必坏
reporter: QA
owner: Ops            # 后端①已实现(7df59bb)；球交 Ops 做②nginx+prod env，前端做③dev /img，齐后 QA 验
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
- 2026-06-04 [用户/QA] **方案拍板：nginx 静态反代图片目录 + 后端返「尽量绝对」url，暂不鉴权（图无安全顾虑）。**
  放弃前端 file:// 改写(A)，统一走后端返可用 url。落地三块（QA 给精确规格，不代改）：

  **① 后端（开发，image-code）——把出图 url 从 file:// 改成 web 绝对地址：**
  - `config/settings.py` 加 `image_public_base_url: str = ""`（env `IMAGE_PUBLIC_BASE_URL`）。
  - `infrastructure/storage/local.py` `LocalImageStore`：构造加 `public_base_url: str`；
    `save()` 末行 `return path.resolve().as_uri()` 改为 → `return f"{self._public_base_url}/img/{name}"`
    （`public_base_url` 非空=绝对 `https://host/img/<sha16>.png`；为空回退相对 `/img/<sha16>.png`，同源也可用）。
  - `composition.py:89` 构造改 `LocalImageStore(settings.image_output_dir, public_base_url=settings.image_public_base_url)`。
  - 效果：**所有出图 url（listing SSE `image_generated` + 项目候选图）统一 → `…/img/<sha16>.png`**，前端 `<img src>` 零改动即可显示。
  - 注：出图 url 在**后台任务**里生成（无 HTTP 请求上下文，拿不到 request.base_url）→ 绝对地址只能走**配置式** `IMAGE_PUBLIC_BASE_URL`，不能靠请求头推导。
  - `.env`：prod `IMAGE_PUBLIC_BASE_URL=https://203.0.113.10`；dev `http://localhost:3000`。

  **② Ops（image-ops，compose + nginx）——静态反代图片目录：**
  - `deploy/compose.yml` nginx 服务加只读卷：`- /data/docker/design-hub/generated:/usr/share/nginx/img:ro`。
  - `deploy/nginx/conf.d/design-hub.conf` 443 server 内加：
    `location /img/ { alias /usr/share/nginx/img/; autoindex off; expires 7d; access_log off; }`
  - 注：公开读（无鉴权，按用户决定）；`autoindex off` 防目录遍历；文件名 sha 随机。

  **③ dev 一致性（前端，image-web）——让 dev 也服务 /img：**
  - `vite.config.ts` 加一个 `/img/<name>` 静态中间件（alias `../image-code/generated`），与 prod 同路径；
    现有 `/__localimg` 可退役。这样 dev 设 `IMAGE_PUBLIC_BASE_URL=http://localhost:3000` 后 `/img/x.png` 即可出。

  状态=已确认，owner→开发（①为主）；②→Ops、③→前端。改完通知 QA。
  **QA 验收（我）**：① 真服务器 `curl https://203.0.113.10/img/<name>.png` → 200 image/png；
  ② Playwright 本地复跑「上传→出图→结果区浏览器正常回显（不再裂图、无 file:// 报错）」；prod 同验。
- 2026-06-04 [运维] **②(Ops/nginx) 已完成并部署到生产**：
  · compose nginx 加只读卷 `/data/docker/design-hub/generated:/usr/share/nginx/img:ro`
  · nginx 443 加 `location /img/ { alias /usr/share/nginx/img/; autoindex off; expires 7d; access_log off; }`
  · `nginx -t` 通过、重建生效；实测 `curl https://203.0.113.10/img/14ca4f72bb087e83.png` → **200 image/png**（QA 验收①先行达成），`/img/`(目录) → 403 防遍历。
  · 已合入 .github CI（push main 会带上），并直接部署生效。
  **仍待**：① 后端返 `…/img/<sha>.png`（开发，image-code）+ ③ dev 一致性（前端）。
  其中 prod `IMAGE_PUBLIC_BASE_URL=https://203.0.113.10` 这条 env 由运维在①落地后注入服务器 .env（我的域，待开发加好 settings 字段即注入）。owner 维持=开发。
- 2026-06-04 [开发] **①后端已实现**（commit 7df59bb）：`settings` 加 `image_public_base_url`(env
  `IMAGE_PUBLIC_BASE_URL`)；`LocalImageStore` 返回 `{base}/img/<sha16>.png`（base 空→相对 `/img/<name>`），
  不再 file://；`composition` 注入。所有出图 url（listing SSE + 项目候选）统一 `/img/<name>`，前端 `<img src>`
  零改动可显示。**附带必改（QA ①规格漏的跨流耦合）**：出图 url 同时被项目导出读回字节，`LocalExportStore.read`
  只认 file://，改 url 会炸导出 → 改为按 url 文件名从注入的 `source_dir`(出图目录)读，兼容 file://与 web 路径，
  asgi 注入 source_dir。验证 ruff+mypy(187)+冒烟（绝对/相对 url、导出三形态 url 读回同字节、防穿越、app 构建）全绿。
  **②nginx 运维已完成(curl 200)👍。状态→修复中，owner→Ops。仍待**：
  (a) **运维**：注入 prod `.env` `IMAGE_PUBLIC_BASE_URL=https://203.0.113.10` + **用含本提交的代码重建 api 镜像**
  （否则容器内仍是旧 file:// 逻辑）；(b) **前端③**：dev `vite.config.ts` 加 `/img/<name>` 中间件 + dev
  `IMAGE_PUBLIC_BASE_URL=http://localhost:3000`（仅 dev 一致性，prod 不依赖）。(a) 就位后 QA 按本条验收 prod。
