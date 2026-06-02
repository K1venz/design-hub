---
id: ISSUE-0016
title: 缺静态图床 —— 素材/候选图 url 为 mock://、file://，前端无法显示缩略图
status: 待确认
severity: P2
reporter: 前端
owner: 开发
created: 2026-06-02
updated: 2026-06-02
related:
  - code: image-code/infrastructure/storage/ · providers（图 url 生成）
  - 前端: image-web/src/components/generate/ImageThumb.tsx
  - 接口: GET /jobs/{id}/images · GET /projects/{id}/assets · GET /projects/{id}/images
---

## 现象
前端选稿(FE-3)/素材(FE-2)/导出(FE-5) 都要显示图，但后端返回的图 url **浏览器无法加载**：
- 真实 gpt-image：`file:///.../generated/xxx.png`（本地路径，浏览器禁止跨源 file://）。
- Mock provider：`mock://lingdong-2/0.png`（伪 scheme）。
- 素材同理：`file:///.../assets/xxx.png`。

→ 前端只能显占位图标（`ImageThumb` 已做 onError 兜底）。**选稿看不到图无法有效挑选**，体验受损。

## 期望
图 url 可经 HTTP 加载（如 `GET /files/...` 或 `/static/...` 静态路由，或返回带签名的可访问 URL）。
前端 `ImageThumb` 仅渲染 `http(s)/data/blob` 开头的 url，后端给出可访问 url 后自动显示真图，前端零改动。

## 建议方案（后端，择一）
1. 加只读静态路由：`GET /files/{store}/{path}` 经 ImageStore/AssetStore 读本地文件流式返回（需鉴权或签名防越权）。返回的 ImageOut/AssetOut.url 改为该 HTTP 地址。
2. Mock provider 返回可渲染占位图（如 `https://placehold.co/...` 或 data URL），便于无真实出图时联调选稿视觉。
3. 部署期接 OSS：url 为对象存储签名地址。

> 倾向 1（统一图床）+ 2（Mock 出可视占位，方便免费联调选稿）。

## 影响
- 不阻塞 FE-2/3/5 的**功能**（上传/评分/保留/导出参数都不依赖能看到图），但**选稿/交付的视觉环节缺失**。
- 前端已用占位兜底，后端补图床后自动显示。

## 处理记录
- 2026-06-02 [前端] FE-3 选稿落地时发现图 url 不可渲染，开条目指给开发。
