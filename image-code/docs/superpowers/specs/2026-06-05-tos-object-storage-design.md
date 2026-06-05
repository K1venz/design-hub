# 设计：接入火山引擎 TOS 对象存储（私有桶 + 预签名 url）

- 日期：2026-06-05 · 角色：开发（image-code）· 状态：用户已批准（私有+签名 url，scope C）

## 目标 / 范围
出图结果(`ImageStore`)与 listing 上传图(`UploadStore`)迁到火山引擎 TOS（S3 兼容，SDK `tos`）。
两桶**私有**，前端经后端**预签名 url（pre-signed GET，默认 1h）**直连 TOS 取图。
`AssetStore`(项目素材)/`ExportStore`(导出) 本期不迁。LSP 替换，**不碰业务层**。

- 桶：`bucket-design-hub-generate`(出图) / `bucket-design-hub-upload`(上传)；region `cn-shanghai`，endpoint `tos-cn-shanghai.volces.com`。
- 凭据 AK/SK 进 `.env`（gitignored）。连通性已实测：两桶 put/get/delete OK。

## 关键抽象：MediaUrlSigner（key → 可访问 url）
私有桶下 url 不能静态拼，要按请求签。新增端口：
```
class MediaUrlSigner(ABC):
    def generated_url(self, key: str) -> str   # 出图结果 image_key → url
    def upload_url(self, key: str) -> str       # 上传图 upload_key → url
```
- `LocalMediaUrlSigner(base_url)`：`{base}/img/{key}`（dev/fallback，复用 ISSUE-0029 的 nginx /img）。
- `TosMediaUrlSigner(client, generate_bucket, upload_bucket, ttl)`：各桶 `pre_signed_url(GET, bucket, key, expires=ttl)`。

## 适配器（infrastructure/storage/tos.py）
- `build_tos_client(settings)` → `tos.TosClientV2(ak, sk, endpoint, region)`。
- `TosImageStore(ImageStore)`：`save(bytes,suffix)` → key=`{sha16}{suffix}`，`put_object(generate_bucket,key,bytes)`，
  返回 `signer.generated_url(key)`（签名 url，供 SSE 即时显示）。
- `TosUploadStore(UploadStore)`：`save(bytes,content_type)` → key=`{sha16}.{ext}`，`put_object(upload_bucket,...)` → 返回 key(id)；
  `load(id)` → `get_object(upload_bucket,id).read()` + content_type（喂 /images/edits / 预览代理）。

## 装配切换（composition）
`build_image_store/build_upload_store/build_media_signer(settings)`：配了 `tos_access_key`+两桶 → 用 Tos*；否则回退 Local*。
- `build_gpt_image_provider` 用 `build_image_store`。
- asgi：`upload_service=UploadService(build_upload_store)`；`app.state.media_signer=build_media_signer`。

## 集成（私有 → 按请求签）
- **listing 历史**：`listing_history_schemas.*.of(model, signer)` 用 `signer.generated_url/upload_url` 拼图；
  路由 `list_jobs`/`get_job` 用 `app.state.media_signer`（替原 `image_public_base_url`）。
- **SSE**：`TosImageStore.save` 已返回签名 url → `GeneratedImage.url` 即可显示，命令无需改 SSE。
- **命令取 image_key**：`commands._image_key` 改成"去 ?query 再取文件名"（签名 url 带 query）。
- **上传预览**：`GET /uploads/{id}` 仍走 `UploadStore.load` 字节代理（TosUploadStore.load 从 TOS 下载），私有天然支持。

## 配置（settings + .env）
`tos_access_key/secret_key:SecretStr`、`tos_region`、`tos_endpoint`、`tos_generate_bucket`、`tos_upload_bucket`、`tos_signed_url_ttl:int=3600`。

## 验证（无 pytest）
ruff + mypy（tos 无 stub → pyproject 加 mypy override ignore_missing_imports，沿用项目对 untyped 库的既有做法）
+ 冒烟：本地 signer 拼接；**真实 TOS** put → 签名 url → 取图回字节一致 → 清理。

## 影响 / 风险
- ImageStore/UploadStore 端口签名不变（LSP）；listing 命令/历史 url-building 改为经 signer。
- 海报流 job_repository 存 GeneratedImage.url——切 TOS 后存的是签名 url（带 query、会过期）。海报历史回看
  需另处理（本期 listing 优先；poster 走 0030 之外，标注为后续）。
