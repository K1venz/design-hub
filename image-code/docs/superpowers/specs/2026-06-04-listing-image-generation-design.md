# 设计：电商 Listing 一键出图（轻量链路）后端设计

- 日期：2026-06-04
- 角色：开发（image-code）
- 范围：仅后端切片。前端 UI、需求归档、话术文案由其它角色经 image-issues 联动。
- 状态：待用户复核

## 1. 背景与目标

参考竞品 designkit.cn 的 product-kit 形态，做一个"电商 listing 一键出图"轻交互：
上传同一产品的 ≤3 张原图 + 若干下拉（电商平台 / 国家地区 / 语言 / 比例）+ 一段
"商品卖点&要求"文本 + 一个"张数"下拉（1–7）→ 一键调用 gpt-image-2 图生图，出 N 张。

这是一种**比现有"项目→需求单→选模板族→重编排出图"更轻的产品形态**。MVP 不做镜头分型，
只是同一份合成 prompt 出 N 张候选。

### 与现有 PRD 的关系（重要）
- PRD §3.1/§3.2 把 V1 核心写成「BiRefNet 抠图 + 两阶段合成」。该方向已被用户拍板的
  「不抠图、gpt-image-2 直接出、提示词是唯一杠杆」取代，实际代码（`openai_compat.py`）也就是
  直接打 `/images/edits`。**本设计建在"直接 edit"之上**，不走两阶段合成。
  → 需 PM 在 PRD 标注此脱节并补本功能定义（见 §8 派单）。

### 非目标（YAGNI / 押后排期）
- 镜头分型：主图白底 / 特写细节 / 使用场景 / 卖点信息图 / 尺寸说明 / 生活方式 / 对比图。
- "自定义配置" / "智能匹配（AI 分析商品图选套图）"。
- "AI 帮写"按钮。
- listing 出图历史的持久化（MVP 不存，仅留架构口子，见 §6）。

## 2. 关键决策（已与用户确认）

| # | 决策 | 结论 |
|---|---|---|
| 1 | prompt 拼接放前端还是后端 | **后端**（质量命脉，需版本化 / 可测 / 多端一致） |
| 2 | 下拉如何传输 | **当数据传**：通用 `modifiers` key→value 袋子，增删下拉不改 schema |
| 3 | 比例(ratio) | **单独成字段**，落成真实 `size` 参数（光写进 prompt 文字模型不可靠） |
| 4 | 未知下拉值 | **fail-fast 报错**；种子表覆盖所有下拉值，正常不触发 |
| 5 | 出图历史 | MVP **不持久化**，但留端口口子，将来换实现即可 |
| 6 | 同步 vs 异步 | **异步**：gpt-image-2 edit 单次 ~187s，N 张更久，必走队列 + SSE |

## 3. 架构总览

新增一条独立的 listing 出图链路，**复用**基础设施（Provider / CostGuard / ImageStore /
异步队列 / SSE / 落库端口），**不复用**重编排（PromptOrchestrator / ModelRouter）——
后者是海报流的，listing 流不需要，且 live edit 模型只有 gpt-image-2 一个，路由无意义。

```
前端(image-web)
  └─ POST /listing/generate (multipart) ──► interface/api/routes/listing.py
                                              │ 解析 → ListingGenerateRequest
                                              ▼
                                  application/listing/listing_service.py
                                              │ 1) prompt_composer 组装 prompt
                                              │ 2) CostGuard 预扣
                                              │ 3) gpt-image-2 edit(≤3图, size, n)
                                              │ 4) CostGuard 回正 + (口子)历史
                                              ▼
                                  异步队列 + SSE 进度（复用现有）
  └─ GET /listing/{job_id}/events (SSE) ◄──── 进度/结果 URL
```

## 4. API 契约

### 4.1 出图（异步，立即返回 job_id）
```
POST /listing/generate            Content-Type: multipart/form-data
  鉴权：Bearer（复用现有）
  字段：
    images:         file × (1..3)        # 同一产品原图；超过 3 或为 0 → 400
    selling_points: str                  # "商品卖点&要求"文本
    ratio:          str                  # 形如 "1:1"；映射到 size，见 §4.3
    n:              int   1..7           # "张数"下拉；越界 → 400
    modifiers:      str(JSON)            # {"platform":"亚马逊","country":"中国","language":"中文"}
  返回：{ "job_id": "<hex>" }
```
- `modifiers` 是通用 key→value 袋子。**增删 / 复用下拉框 = 只改后端片段表（§5），契约不动、schema 不动**，前端只多/少塞一个 key。
- 校验在边界完成（fail-fast）：images 数量、n 范围、ratio 合法、modifiers 可解析。

### 4.2 进度（SSE，复用现有方案）
```
GET /listing/{job_id}/events       鉴权：?access_token=（原生 EventSource 不能带头，沿用 ISSUE-0011）
  事件流：进度 / 单张完成（含 url/seed/latency/cost）/ 全部完成 / 失败
```

### 4.3 ratio → size 映射（种子表，最终值由 PM 定）
gpt-image-2 实际支持的尺寸有限，先给一份能跑的种子映射：

| ratio | size |
|---|---|
| 1:1  | 1024x1024 |
| 3:4  | 1024x1536 |
| 4:3  | 1536x1024 |
| 9:16 | 1024x1536 |
| 16:9 | 1536x1024 |

> 不在表内的 ratio → 400（fail-fast）。具体支持哪些比例、非方形是否走 1024x1536 由 PM/调研定。

## 5. Prompt 组装（服务端，可版本化 / 可测）

新增 `application/listing/prompt_composer.py`：

- `PromptModifierRegistry`：`(field, value) → 片段模板`。种子值（最终文案由 image-prompt 出）：
  - `("platform","亚马逊") → "用于亚马逊电商平台的商品展示图"`
  - `("country","中国") → "商品适用于中国市场"`
  - `("language","中文") → "广告文字使用中文"`
  - …（覆盖前端首版所有下拉值）
- `compose(selling_points: str, modifiers: dict[str,str]) -> str`：
  `final = selling_points.strip() + "。" + "；".join(片段 for 每个 modifier)`
- **未知 `(field,value)` → 抛 `DomainError`（fail-fast）**，不静默跳过。前后端版本不同步当场暴露。
- 纯函数、无 I/O → 单元测试直接覆盖（QA 可验证质量命脉）。

> 注：本组装器**独立于**现有 `PromptOrchestrator`，不做兼容层、不互相依赖。两者是两种产品形态。

## 6. 生成流程与持久化

### 6.1 ListingGenerationService（application/listing/listing_service.py）
1. `prompt = composer.compose(selling_points, modifiers)`
2. `size = ratio_to_size(ratio)`
3. `CostGuard.precheck_and_reserve(user_id, estimate(n))`
4. `provider.generate(prompt=prompt, negative_prompt="", reference_images=<≤3图>, size=size, n=n)`
   - 直连 gpt-image-2（live edit provider）。失败按 I/O 域允许重试（provider 内已有）。
   - 异常 → `CostGuard.rollback`，向上抛。
   - ⚠️ 实现期风险：中转站的 `/images/edits` 对 `n>1` 是否一次返回多张待验证。若不支持，
     退化为**并发 N 次单图 edit**（每张单算成本/seed）；该差异封装在 service/provider 内，
     不影响 API 契约。
5. `CostGuard.reconcile(reserved, actual)`
6. `history.record(...)`（MVP 为空实现，见 6.3）
7. 经 SSE 推送每张结果（url/seed/latency/cost）+ 全部完成。

### 6.2 真改点（现有代码适配新架构，非加补丁）
- **真改 1 — 多图 edit**：`infrastructure/providers/openai_compat.py:_edit` 现在写死
  `reference_images[0]`（只用第一张）。扩成把 ≤3 张都作为 multipart `image[]` 发送。
  端口 `model_provider.generate` 已是 `reference_images: list[bytes]`，签名不变。
- **真改 2 — 异步任务泛化**：现有 `TaskQueue.enqueue(job_id, brief, user_id)` +
  `task_runner` 写死跑 `pipeline.run(brief)`。泛化为**命令模式**：队列承载一个
  `GenerationCommand`（抽象 `async run() -> GenerationResult`）。
  - 海报流：`PosterCommand`（包 brief + pipeline）——**老代码适配新接口**。
  - listing 流：`ListingCommand`（包 listing_service 调用参数）。
  - `task_runner` 只 `result = await cmd.run()` 后落库 + SSE。
  - ⚠️ 影响面：触及现有异步/SSE 共享层，海报异步路径与其测试需随之调整。

### 6.3 历史持久化口子（MVP 不存）
- 新增端口 `ports/listing_history.py`：`async def record(user_id, prompt, result) -> None`
- MVP 装配 `NoOpListingHistory`（什么都不做）。
- 生成的图片 URL 仍经 provider/ImageStore 得到并经 SSE/结果返回——"不存历史"指**不写历史记录表**，
  不影响本次结果可见。
- 将来服务器空间够了：在 `composition.py` 把绑定换成 DB 实现（可复用 `job_repository.save_completed`，
  其 `project_id` 已可为 None）。**业务代码零改动**。

## 7. 成本 / 鉴权 / 错误处理
- 成本：N 张 × gpt-image-2 单价，CostGuard 预扣 → 按实回正（复用，含 ISSUE-0009 对账）。
- 鉴权：出图走 Bearer；SSE 走 `?access_token`（ISSUE-0011）。
- 错误处理（遵守 fail-fast）：
  - 边界校验失败（图数 / n / ratio / modifiers 解析 / 未知下拉值）→ 4xx，不降级。
  - provider 网络/IO 失败 → 允许重试 / 同模型备用（I/O 域，已有），耗尽则失败回滚预扣。

## 8. 跨角色派单（开 image-issues，owner 指给对方）
1. **PM**：本功能补进 PRD；标注 §3.1/§3.2 两阶段合成已被"直出"取代；定下拉选项清单
   （平台/国家/语言/比例的取值）、张数上限、ratio 支持范围、验收标准。
2. **image-prompt**：产出「下拉值 → 话术片段」正式中文文案（替换 §5 种子表）。
3. **image-web**：按 §4 契约实现前端 UI（≤3 图上传、4 下拉、卖点文本、张数、SSE 进度）。
4. **QA**：本功能测试用例（待 PM 出验收标准后）。

## 9. 受影响 / 新增文件清单（预估）
新增：
- `interface/api/routes/listing.py`
- `interface/listing_schemas.py`
- `application/listing/prompt_composer.py`
- `application/listing/listing_service.py`
- `application/listing/commands.py`（GenerationCommand / PosterCommand / ListingCommand）
- `ports/listing_history.py`
- `infrastructure/listing_history_noop.py`

改动：
- `infrastructure/providers/openai_compat.py`（多图 edit）
- `ports/task_queue.py` + 异步 `task_runner` + 海报异步路由（命令模式泛化）
- `composition.py`（装配新链路 + NoOp 历史）
- `interface/api/app.py`（挂 listing 路由）

## 10. 验收（后端自验，QA 正式验收另定）
- `/listing/generate` 多图 + modifiers 能入队返回 job_id；非法入参 4xx。
- prompt_composer 单测：已知下拉值正确拼接；未知值抛错。
- 多图 edit 真发 ≤3 图到 `/images/edits`。
- 异步命令模式：海报流与 listing 流都能经同一队列/SSE 跑通。
- ruff + mypy 全过。
