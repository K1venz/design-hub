---
id: ISSUE-0031
title: listing 历史详情「输入产品图」回显 404——input_urls 指 /img/(generated) 但上传文件落 assets/
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 历史详情里输入图永远裂图（输出候选图正常）；不阻断出图，但历史回看不完整
reporter: QA
owner: QA             # prod 已被 TOS 迁移顺带修；交 QA 复验。本地 dev 残留低优先
created: 2026-06-05
related:
  - test: image-qa/listing_history_e2e.py（用例5 输入图 url GET→404）
  - code: image-code/src/design_hub/interface/listing_history_schemas.py（input_urls = {base}/img/{upload_key}）
  - code: image-code/src/design_hub/interface/api/asgi.py:133（UploadService→LocalUploadStore(asset_output_dir)，上传落 assets/）
  - issue: ISSUE-0029（/img 只反代 generated/）、ISSUE-0030（历史复用 /img）
---

## 现象
listing 历史详情 `GET /listing/jobs/{id}` 的 `input_urls`（输入产品图）GET → **404**，前端回显裂图。
输出候选图 `images[].url`（generated/）GET → 200，正常。

## 根因（QA e2e 实测 + 读码）
- 上传文件落 **`assets/`**：`asgi.py:133` `UploadService(store=LocalUploadStore(settings.asset_output_dir))`。
- 详情 `input_urls` 拼 **`{IMAGE_PUBLIC_BASE_URL}/img/{upload_key}`**（listing_history_schemas `_img_url`）。
- 但 `/img/`（ISSUE-0029 nginx）只 alias **`generated/`** → `/img/<upload_key>` 在 generated/ 找不到（文件在 assets/）→ 404。
- 实测：`listing_history_e2e.py` 用例5：输出图 `…/img/0d92feb99fbab119.png`→**200 image/png**；
  输入图 `…/img/d5d91fe1a404ec2d.png`→**404**（文件实在 assets/）。

## 期望 vs 实际
- 期望：历史详情输入图与输出图都能回显（GET→200 image/*）。
- 实际：输入图 404（generated/ 无此文件）。

## 修复方案（任一，开发/Ops 协调，PM 定）
1. **Ops + 后端**：nginx 再加 `location /img-input/ { alias …/assets/; autoindex off; }`；后端 `input_urls` 改用 `{base}/img-input/{upload_key}`。（输入/输出分目录服务，清晰）
2. **后端统一存储**：上传也落 `generated/`（或同一公开图目录），`/img/` 一处服务全部。需评估与素材流(`asset_output_dir`)是否冲突。
3. **Ops**：让 `/img/` 同时覆盖 generated/ + assets/（如把两者放同一父目录或加第二 location 映射），后端零改。

## 处理记录
- 2026-06-05 [QA] ISSUE-0030 历史 e2e（真 MySQL+真 gpt-image）发现：输出图回显 200、**输入图回显 404**。
  定位 input_urls→/img/(generated) 与上传落点 assets/ 不一致。开单，owner=开发（与 Ops 协调图床目录）。
- 2026-06-08 [开发] **prod 已被 TOS 迁移顺带修**（commit b308556，随 ISSUE-0033 上 prod）：
  历史 schema 的 `input_urls` 已从写死 `/img/{key}` 改为 **`signer.upload_url(key)`**——TOS 部署下签的是
  **upload 桶**（上传图就在那）→ 输入图可显示，根因（input/输出指错目录）消除。
  · **本地 dev 残留（低优先）**：`LocalMediaUrlSigner.upload_url` 仍返 `/img/{key}`（=generated/），本地上传在
    assets/ → 仍 404；且私有上传 `<img>` 无法带 token，本地预览本就受限。dev-only，prod 不受影响。
  状态→待验证，owner→QA。**请 QA**：在 prod/TOS 环境复验历史详情**输入图**——url 应为 upload 桶预签名、GET 200。
- 2026-06-08 [开发] **本地 dev 残留判定：按设计不修（won't-fix）**。ISSUE-0032 把上传图改为**按用户私有命名空间**后，
  本地 dev 输入图无法用裸 `<img>` 显示（私有 + `<img>` 不能带 token，同 ISSUE-0011 约束）——改 url 也救不了显示，
  这是 per-user 隐私隔离的必然结果、非缺陷。**prod 已由 TOS 预签名 url 解决**（输入图走 upload 桶签名 url）。
  本地 dev 若需预览，前端可 authGet+blob（前端按需，非后端项）。→ 本条 **prod 经 QA 复验通过即可关闭**，无后端遗留。
