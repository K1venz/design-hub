---
id: ISSUE-0031
title: listing 历史详情「输入产品图」回显 404——input_urls 指 /img/(generated) 但上传文件落 assets/
status: 待确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 历史详情里输入图永远裂图（输出候选图正常）；不阻断出图，但历史回看不完整
reporter: QA
owner: 开发           # input_urls 路径=后端；图床服务目录=Ops；二者协调，主开发
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
