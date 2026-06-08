---
id: ISSUE-0028
title: 前端图片上传失败只显示"error"，吞掉后端 400 原因（>10MB/格式不支持），用户不知为何失败
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 不阻断功能，但用户无法自助排错；体验问题
reporter: QA
owner: QA             # 前端已修(透传 detail + 客户端预校验 + 限制提示)，待 QA 验
created: 2026-06-04
related:
  - 前端: image-web/src/components/listing/ImageUploader.tsx（.catch(() => patch(key,{status:'error'})) 丢弃 error）
  - 前端: image-web/src/api/listing.ts（useUploadImage）
  - code: image-code/src/design_hub/application/listing/upload_service.py（_MAX_BYTES=10MB；白名单 png/jpeg/webp）
---

## 现象
用户在 listing 上传图片，前端显示上传失败（error 态），但**不显示任何原因**，用户不知如何处理。

## 根因（QA 实测 + 读码定位）
1. **后端正确返回 400 + 原因**（非崩溃）：`UploadService` fail-fast——
   - 超过 10MB → `{"error":"bad_request","detail":"图片超过 10MB（… 字节）"}`
   - 格式非 png/jpg/webp（如 iPhone **HEIC**）→ `{"detail":"不支持的图片格式：image/heic（仅 png/jpg/webp）"}`
   （QA 实测：真实 jpg/png 上传 **200 成功**；>10MB 与 image/heic 各复现上述 400。）
2. **前端吞掉了 detail**：`ImageUploader.tsx` `upload…catch(() => patch(key, { status: 'error' }))`
   —— 只置 error 态，未读取/展示后端返回的 `detail`。用户只看到"失败"，无从知道是「太大」还是「格式不对」。

## 期望 vs 实际
- 期望：上传失败时显示后端原因（"图片超过 10MB" / "仅支持 png/jpg/webp"），并最好前端预校验大小/格式 + 提示限制。
- 实际：只显示 error，原因被吞。

## 建议修复（前端）
1. `catch` 里读后端 `detail`（`await res.json()` 取 `detail`）并展示到该图条目/toast。
2. 上传前**客户端预校验**：`file.size > 10MB` 或 `type ∉ {image/png,image/jpeg,image/webp}` 直接提示，不发请求。
3. 上传区提示文案标注「≤10MB，png/jpg/webp」；iPhone HEIC 建议提示转 jpg（或后端将来支持 HEIC 转码，需 PM 定）。

## 处理记录
- 2026-06-04 [QA] 本地起整栈供用户自测，用户报「点上传失败」。后端日志 4×`POST /uploads 400`；
  复现确认=后端校验拒（>10MB 或非 png/jpg/webp），但前端 `.catch` 吞掉 detail 致用户无从排错。开单指前端。owner=前端。
- 2026-06-08 [前端] **已修**（建议 3 条全做）：
  ① `useUploadImage` 解析后端 `{detail}`，抛清晰文案（非 `res.text()` 裹原文）；
  ② `ImageUploader` 失败 `.catch` 读 err.message → 写到该图条目(error 态 title 悬停) + `toast.error` 弹原因；
  ③ **客户端预校验** `rejectReason`：`type∉{png,jpeg,webp}` 或 `size>10MB` 直接 toast 拒、不发请求；
  ④ 上传区加限制提示「≤10MB · png/jpg/webp」。HEIC 转码归后端/PM（本期仅提示不支持）。
  typecheck/lint/build/vitest 全过。状态=待验证，owner=QA（请验 >10MB / HEIC / 正常 三态文案）。
