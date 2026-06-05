---
id: ISSUE-0033
title: 运维上线火山引擎 TOS 对象存储——prod 注入 TOS_* + 重建 api 镜像
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 生产配置/部署；不配则 prod 仍走本地磁盘+nginx /img（功能可用，未上 TOS）
reporter: 开发
owner: 运维           # prod .env 注入 + 镜像重建 + 验证
created: 2026-06-05
related:
  - code: image-code/docs/superpowers/specs/2026-06-05-tos-object-storage-design.md
  - code: image-code/src/design_hub/config/settings.py（TOS_* 字段）
  - code: image-code/src/design_hub/composition.py（build_image_store/upload_store/media_signer 切换）
  - issue: ISSUE-0029（出图 url /img 已上 prod，TOS 接替）、ISSUE-0030（listing 历史存 key）
---

## 背景
后端已接入火山引擎 TOS 对象存储（私有桶 + 预签名 url），代码已合并（commit b308556），
本地真实出图端到端验证通过（出图→TOS generate 桶→签名 url 取回真实图）。
**机制**：配了 `TOS_ACCESS_KEY` + 两桶则用 TOS 适配器，否则回退本地（LSP，零代码改动切换）。
现需运维把这套配置上 prod。

## 需运维做（image-ops）
1. **prod 服务器 `.env` 注入以下 `TOS_*`**（沿用现有部署 .env，权限 chmod 600，不入库）：
   ```
   TOS_ACCESS_KEY=<AK>            # 火山引擎访问密钥；值由用户单独提供，不在本 issue（密钥不入库）
   TOS_SECRET_KEY=<SK>
   TOS_REGION=cn-shanghai
   TOS_ENDPOINT=tos-cn-shanghai.volces.com
   TOS_GENERATE_BUCKET=bucket-design-hub-generate
   TOS_UPLOAD_BUCKET=bucket-design-hub-upload
   TOS_SIGNED_URL_TTL=3600
   ```
   - **AK/SK 值找用户拿**（用户已有；建议火山引擎子账号最小权限：只授这两桶读写）。
2. **重建 api 镜像并重启**：依赖 `tos==2.9.1` 已进 pyproject/uv.lock（随 main），重建即带上。
3. 重启后 api healthy、站点 200。

## 验证（运维侧）
- 容器内 `Settings().tos_generate_bucket == 'bucket-design-hub-generate'` 且 `tos_access_key` 非空。
- 真实出图一张（或等前端/QA 联调）：图落 TOS generate 桶；SSE/历史返回的 url 形如
  `https://bucket-design-hub-generate.tos-cn-shanghai.volces.com/<sha>.png?X-Tos-...`，浏览器能打开显示。

## ⚠️ 注意点（运维/PM 知会）
1. **老图不在 TOS**：切 TOS 后，**TOS 之前已落本地 `generated/` 的老图**不会自动在 TOS——其 image_key
   经 TOS 签名 url 会 404。listing 历史是新功能、prod 真实数据极少（多为测试），影响可忽略；
   若有要保留的老图，需先把本地 `generated/` 文件搬上 TOS（本期不做）。
2. **nginx `/img/` 变冗余**：上 TOS 后出图 url 走 TOS，不再用 nginx `/img/`（ISSUE-0029）。
   留着无害（老图本地仍可经它访问），要不要退役由你定，不急。
3. **海报流已知限制**：`ImageStore` 海报流也共用，切 TOS 后海报 `generated_image.url` 存的是会过期
   的签名 url，海报历史回看过期——本期 listing 优先，海报另议（开发侧待排）。

## 期望 vs 实际
- 期望：prod 出图/上传图落 TOS 私有桶，前端经预签名 url 直连 TOS 显示。
- 实际：prod 现走本地磁盘 + nginx /img（ISSUE-0029），未上 TOS。

## 处理记录
- 2026-06-05 [开发] TOS 接入完成（b308556）+ 本地真实出图端到端验证通过；开本条派运维上 prod。
  AK/SK 值找用户拿（密钥不入库）。owner=运维，status=已确认。
