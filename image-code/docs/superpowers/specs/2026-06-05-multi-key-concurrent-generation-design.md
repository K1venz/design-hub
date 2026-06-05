# 设计：多 key 轮询 + listing 单任务 N 张并发出图

- 日期：2026-06-05
- 角色：开发（image-code）
- 状态：用户已批准 A+B（并发度 OK、不加限流）

## 目标
1. **A** 出图 provider 支持多 API key，按请求 round-robin 分发——并发出图请求自动散到多 key，缓解单 key 限流。
2. **B** listing 单任务出 N 张改为 **N 个并发单图请求**（每张轮询 key），耗时从串行 N×~108s 压成 ≈ 单张 ~108s；部分失败容错对接 ISSUE-0030 的「部分完成」。

## A：provider 多 key 轮询
- 配置：`GPT_IMAGE_API_KEY=key1,key2`（逗号分隔；单 key 无逗号照旧，不改字段名）。
- `OpenAICompatImageProvider`：构造 `api_key: str` → `api_keys: list[str]`（非空）；新增 `_next_key()` 原子计数器
  `keys[idx % n]`；`_request_json`/`_request_multipart` 的 `Authorization` 头改用 `_next_key()`（每次 HTTP 请求取一个）。
  - 并发安全：asyncio 单线程，计数器自增不跨 await，round-robin 足够均匀。
  - 重试取下一个 key（天然分散，限流时换 key 更可能成功）。
- `composition.build_gpt_image_provider`：`gpt_image_api_key.get_secret_value().split(",")` → strip/去空 → `api_keys`。

## B：listing N 张并发单图
- `ListingGenerationService.generate`：替换单次 `provider.generate(n=N)` 为
  `asyncio.gather(*[provider.generate(n=1, seed=i) for i in range(n)], return_exceptions=True)`。
  - 每个 call 经 A 轮到不同 key；seed=i 区分各张。
  - **部分失败容错**（I/O 域）：收集成功的图；≥1 成功 → `reconcile`(按成功张数) + 返回成功图；全失败 → `rollback` 预扣 + 抛首个异常。
  - 返回的 `ListingResult.images` 可少于 n → `ListingGenerationCommand` 既有逻辑落 `完成`(满 N)/`部分完成`(不满)/`失败`(全挂)。成本预扣 n×unit_cost、按实回正不变。
- **作用域**：仅 listing service。**不碰海报流**（poster 仍 `generate(n=N)` 一次；n>1 对上游的支持归 ISSUE-0025/QA，单独处理）。

## 影响面
- 改：`infrastructure/providers/openai_compat.py`(A)、`composition.py`(A)、`application/listing/listing_service.py`(B)、`.env`(A，gitignored)。
- 不动：provider 端口签名（仍 `generate`）、listing 命令/路由/历史、海报流、poster pipeline。

## 验证（无 pytest，门=ruff+mypy+冒烟）
- A：注入假 client，多次请求 → Authorization 头在多个 key 间轮转。
- B：Mock provider，n=4 → gather 出 4 张、各 seed 0..3；一个 call 抛错 → 返回 3 张（部分完成路径）；全抛 → service 抛错 + rollback。
- 真实：配 .env 两 key 后查 `/v1/models` 确认其对当前 `GPT_IMAGE_MODEL` 的访问权限（避免 vip/非 vip 不匹配）。

## 安全
- 两个 key 仅入 `.env`（gitignored），代码不含 key 明文，不入库。
