# ISSUE-0065 异步出图 Provider — 端口演进设计（一页提案）

## 0. 当前接入决策（2026-07-24）

当前 GPT Image 2 主路径改为中转站 OpenAI 兼容 Images API：

- Base URL：`https://api.yhlxj.ai/v1`
- 生图：`POST /images/generations`
- 参考图编辑：`POST /images/edits`
- 模型：`gpt-image-2`
- 多参考图：multipart 重复同名 `image` 字段
- 单次数量：`n=1`
- 响应：遍历 `data`，读取 `url` 或 `b64_json`
- 保真：仅 edits 发送 `input_fidelity=high`
- 双 Key：同一个 `api_key_env` 环境变量用逗号分隔，provider 按请求轮换；瞬时错误重试会切换下一把 Key

依据：APINebula `gpt-image-2-1k` 文档明确建议一次请求的生图/编辑优先使用 Images API。
下文保留异步任务 provider 的历史设计与备用能力说明，但它不再是当前 GPT Image 2 默认连接。

> 目的：把出图从同步端点（新 key 分组下过载、prod 成功率 ~33%）迁到 apinebula 异步任务端点
> （排队消化、失败自动退款、实测零「临时繁忙」）。dev 出稿待 coordinator 技术过后动码。

## 1. 已确认上游契约（coordinator #1107 实证，¥0.8）
- **Base URL**：`https://apinebula.ai/v1`。旧地址 `https://apinebula.com/v1`
  在 2026-07-24 实测连接超时；同一 Key 请求新地址可正常通过鉴权并返回规范参数错误。
  配置迁移仅把“异步 provider + 精确旧地址”改到新域名，并记录实际修改的配置名；
  downgrade 只恢复这些记录，避免误改原本已配置新域名的行。
- **submit** `POST https://apinebula.ai/v1/image-tasks/edits`，JSON：
  `{model, prompt, quality?, size:"WxH", input_fidelity?, images:[{image_url}]}`；无参考图走
  `/image-tasks/generations` 同形无 `images`。Bearer 鉴权、服务端自动补 async=true。
- **submit 响应**：`{task_id, status:"queued", ...}`。
- **轮询** `GET https://apinebula.ai/v1/image-tasks/{task_id}?detail=true`，状态枚举
  `queued/in_progress/completed/failed`；
  实测 ~10s 间隔、70s 内完成。
- **完成体**：`detail.data[].download_url`（`cdnimage.apinebula.com` 公网直拉）；**失败体** `error.message`。
- 四问结论：size **被尊重**（1536×1024→1536×1024）、n=2 仍返 1（我们 n=1 免疫）、input_fidelity 接受、
  **prod upload=TOS 预签 URL、worker 直拉成功**（#1104 分支①成立，`MediaUrlSigner.upload_url` 直接可用）。

## 2. 端口演进（核心决策）
现状：`AbstractModelProvider.generate(reference_images: list[bytes], ...)`——参考图传**字节**（launcher
经 `uploads.load` / `image_store.load` 载好、命令→service→provider 透传，套图各子任务复用同一组）。
异步端点要**公网 URL**，不要字节。

**方案（推荐）**：参考图升级为可解析句柄 VO + provider 声明模态，解析留在 launcher（唯一同时握
key+载器+签名器的层），按模态**只物化所需字段**：

```python
# domain/models.py
@dataclass(frozen=True)
class ReferenceImage:
    data: bytes | None = None   # sync provider 用（multipart 字节）
    url: str | None = None      # async provider 用（现签公网 URL）

# ports/model_provider.py
class AbstractModelProvider:
    reference_mode: ReferenceMode = "bytes"   # sync="bytes"（multipart）/ async="url"（json）
    async def generate(self, *, reference_images: list[ReferenceImage], ...): ...
```

- **launcher** 注入 `MediaUrlSigner`，按 `self.service.reference_mode()` 分支：
  `url` 模态→ `ReferenceImage(url=signer.upload_url(key))`（edit 源图走 `generated_url`）**不载字节**；
  `bytes` 模态→ `ReferenceImage(data=await uploads.load(key))` 如旧。
- **sync provider**（`openai_compat`）：`reference_mode="bytes"`，读 `.data` 拼 multipart（其余不动）。
- **async provider**：`reference_mode="url"`，读 `.url` 拼 `images:[{image_url}]`。

> 更小但有浪费的备选：VO 同时载 `data`+`url`、launcher 不分支——async 主路径会白载弃用字节
> （每单 1~3 张 TOS GET）。异步是**主路径**，故推荐分支版免浪费；分支增量落在 launcher 三条路
> （generate/clone/edit 各自已分支，加一层模态判断，增量可控）。

## 3. AsyncImageTasksProvider 内部（后段全复用现有）
`generate()`：① 组 submit JSON（`images=[{image_url}]`、`size`、可配 `input_fidelity`/`quality`）→
POST 拿 `task_id`；② 轮询 5~10s 直到终态，**沿 `retry_max_elapsed` 墙钟**（超时=穷尽 fail-closed
抛 `ProviderTimeout`，同 ISSUE-0055 (i) 语义）；③ `completed`→ `download_url` 拉 bytes→
`ImageStore.save`→ `GeneratedImage`（复用 `_parse` 的 n=1 截断/over-deliver 口径 ISSUE-0045）；
④ `failed`→ `ProviderError(error.message)`（我方预扣由 service `guard.rollback` 回滚，上游自动退款正交）。
submit 段 429/5xx 仍抖动退避重试（复用现有），`queued/in_progress` 非错=继续轮询。

## 4. 0057 注册表接入（两 provider 并存=备用渠道）
- 新 `provider_type="apinebula_async_image"`（现有同步=`openai_compat_image`）。
- `composition.build_gpt_image_provider` 按 `default_config.provider_type` 分派构造哪个类，**连接解析
  `_resolve_image_connection` 复用**（base_url/model/key 同源，仅端点路径与协议不同），均占 registry
  的 `GPT_IMAGE_2` 槽。切换=admin 配 provider_type=async 的默认行 + 重启（同 0042 快照口径）；
  同步 provider 保留、切回默认即回退=备用渠道。前端 0057 配置页零改动（承载 provider_type 字段）。

## 5. 影响面 / 测试
- 改：`domain/models.py`(VO)、`ports/model_provider.py`(签名+模态)、`providers/openai_compat.py`(读 .data)、
  `providers/mock.py`(签名)、`listing_service.py`+`commands.py`(bytes→ReferenceImage 透传)、
  `job_launcher.py`(注入 signer+按模态解析)、`composition.py`+`asgi.py`(async 构造+signer 注入)。
- 新：`providers/apinebula_async.py`。
- 测：async provider 契约（submit shape/轮询状态机/download 落存/失败退款/墙钟超时）用假 httpx
  client（沿 `_SequencedClient` 式）；launcher 按模态解析单测；service/history 现有测随 VO 机械改。

## 6. 待 coordinator 拍的技术点
1. **模态解析位置**：推荐 launcher 分支（免浪费）vs VO 载双（更简但白载）——你定。
2. **失败是否重投**：MVP 拟 `failed`→ 直接失败（不自动重投，上游已内部排队重试）；如需一次重投再加。
3. **并发回调**：异步不压垮上游，`LISTING_CONCURRENCY` 可从止血的 1 调回（套图并行提速）——
   建议异步波稳定后单独调，本条不含。
