---
id: ISSUE-0002
title: M3-a 中转 adapter 缺陷集（错误切换/预算口径/b64/图生图未实现/超时）
status: 已关闭        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: PM
owner: —              # QA 复验通过关闭
created: 2026-05-28
updated: 2026-05-29
related:
  - spec: docs/superpowers/specs/2026-05-28-gpt-image-2-failover-relay-design.md (commit b4c61ca)
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py
  - code: image-code/src/design_hub/infrastructure/providers/failover.py
  - commit: fe1e77b feat(M3-a)
---

## 现象
M3-a (fe1e77b) 已实现 `OpenAICompatImageProvider` + `FailoverModelProvider`，但实现早于产品决策定稿，与 spec（b4c61ca）确认的两条决策及成本约束有 3 处不一致。

## 偏差明细

### ① 错误切换策略未落实（决策①）—— openai_compat.py
`generate()` 用 `response.raise_for_status()`，把**所有** 4xx/5xx 经 `httpx.HTTPError` 统一映射为 `ProviderError`。
- 后果：400/422（提示词违规、参数非法）也会触发 failover 去切备用中转。同一坏 payload 在备用站必然同样失败 → 白烧一次调用 + 拖延，违反 fail-fast。
- 期望（spec §3.1 错误映射表）：
  - 连接错误 / 读超时 / 429 / 5xx → `ProviderTimeout`（可重试，切备）
  - 400 / 422 → `DomainError`（立即上抛，**不切备**）
  - 2xx 响应体非法 → `ProviderError`（视为该家故障，切备）
- 实现要点：需按 `httpx.HTTPStatusError` 的 `response.status_code` 分流，不能一把 `HTTPError` 全归 `ProviderError`。
- **2026-05-29 真实 HTTP 实测（已为决策①补齐硬证据）**：
  - apinebula 坏 size → **400**「不合法的size」、缺 prompt → **422** → 均应 `DomainError` 上抛不切备 ✓
  - apinebula 无权限模型 → **403**、坏 token → **401** → 鉴权/配置类，应上抛（换网关无意义）
  - apinebula 分组无渠道 → **503**、诗云整站宕机 → **502** → 5xx 应 `ProviderTimeout` 切备 ✓
  - ⚠️ **诗云 502 的 body 是 nginx 的 HTML 不是 JSON**：实现必须先按 status_code 分流，**严禁对非 JSON 错误 body 调 `.json()`**（现 M3-a 代码 raise_for_status 在前侥幸不踩，但重构成 status_code 分流时务必显式处理）。
  - 建议直接照搬上表，apinebula 错误码完全是 OpenAI 标准，按 status_code 实现即可。

### ② 预算预留口径错误（决策②）—— failover.py
当前 `self.unit_cost = providers[0].unit_cost`（取主用价）。
- 后果：真切到更贵的备用中转时，`CostEstimator/CostGuard` 预留不足，可能击穿预算红线。
- 期望（spec §3.3）：`self.unit_cost = max(p.unit_cost for p in providers)`，保守预留、按实际出图家结算。
- 附：建议补 `assert all(p.name == providers[0].name for p in providers)`，确保只有同模型中转互备（spec §3.2）。

### ③ 质量档缺失 + b64 取 url 隐患 —— openai_compat.py（已被实测坐实）
- payload 未带 `quality`：gpt-image-2 不指定质量可能默认走最贵档（≈¥1.5/张），与成本约束冲突。最小处理：构造期固定 `quality`（默认 medium）。
- `response_format:"url"` + `item.get("url")` 为空即报错。**实测（诗云）确认：gpt-image-2 返回 `b64_json` 而非 url**（文生图 b64 长 128万字符、图生图 148万字符）。现有实现对诗云会 100% 失败到两家全挂。**必须改为 b64_json 解码**。

### ④【新增 / 严重】图生图(image-to-image)完全未实现 —— openai_compat.py
用户主业务是**图生图**，但现 `generate()` 收了 `reference_images` 参数却**完全没用**，只调 `/images/generations`（纯文生图）。
- 实测：图生图须走 **`POST /images/edits`**（multipart：`image` 文件 + `prompt` + `model` + `n` + `size` + `quality`），诗云已验证可用、质量好（墨镜→金丝圆框、换背景、保风格均准确）。
- 期望：`reference_images` 非空 → 走 `/images/edits`（multipart）；为空 → 走 `/images/generations`。两路返回都按 b64_json 解析。

### ⑤【新增】默认 timeout 过短 —— openai_compat.py
现 `timeout: float = 60.0`。实测诗云：文生图 91s、图生图 102s。60s 会频繁超时误触发 failover。
- 期望：默认 ≥180s（gpt-image-2 是推理型图模型，本就慢）。

## 实测价格（诗云，medium，1024²，2026-05-28）
| 场景 | usage(in/out tokens) | 按官方价折算 | 备注 |
|---|---|---|---|
| 文生图 | 36 / 196 | ≈¥0.044/张 | output token 偏低，疑 usage 失真 |
| **图生图** | 1054(图1024+文30) / 1756 | **≈¥0.44/张** | 输入图吃 1024 image token，**超 1-3毛预算** |
> 注：折算基于官方价×reported usage，**诗云真实扣费含其倍率，须以控制台余额为准**。high 档约为 medium 的 3-4 倍。

## 期望 vs 实际
- 期望：实现严格对齐 spec（b4c61ca）的决策①②与 §6；支持图生图主路径。
- 实际：①②未落实，③已被实测证伪(必须 b64)，④图生图未实现(主业务!)，⑤超时过短。

## 环境 / 上下文
- 路线已定：「gpt-image-2 + 合规」，主备均用能开增值税票的中转（诗云主 / API易备）。
- **主业务=图生图**；图生图 medium ≈¥0.44/张已超 1-3 毛，预算需用户重新拍板（见处理记录）。
- 主备顺序由 composition.py 配置决定（OCP）。诗云实测：返回 b64、延迟~100s、坏请求时遇 429「上游负载饱和」(跑 New API 网关)。

## 处理记录
- 2026-05-28 [PM] 创建并确认（读 fe1e77b 代码核对 spec），状态=已确认，owner=开发
- 2026-05-28 [PM] 诗云 key 实测：坐实③(b64)、新增④(图生图未实现,主业务)、⑤(超时短)，补图生图价格数据。owner 仍=开发
- 2026-05-29 [PM] 选型已定 apinebula 单跑(ISSUE-0003，诗云出局)。装配参考草案见 `docs/superpowers/specs/2026-05-29-composition-apinebula-wiring-draft.md`：**先修本 issue 三项，再按草案接 composition.py**。apinebula 实测：返回 b64、走 /images/edits、延迟~90s、错误码 400/422/403/503 标准(已并入决策①证据表)。owner 仍=开发。
- 2026-05-29 [开发] **五项全部修复**，状态→待验证，owner→QA。提交 `feat(M3): 图生图 /images/edits + ImageStore` 与 `fix(ISSUE-0002): 闭合中转 adapter 五项偏差`：
  - ①错误按 status_code 分流：400/401/403/422→`DomainError`(不切备)；429/5xx→`ProviderTimeout`(切备)；连接/超时→`ProviderTimeout`；**不对非 JSON 错误体调 .json()**（502 nginx HTML 安全）。
  - ②`FailoverModelProvider.unit_cost = max(...)`，并断言仅同模型互备。
  - ③b64_json 解码：经新增 `ImageStore` 端口落点换 url，兼容直接 url。
  - ④图生图 `/images/edits`(multipart 上传产品图)；有参考图走 edits、无走 generations。
  - ⑤默认 timeout 60→**180s**。
  - 附：中转站 `trust_env=False` 直连(境内站绕本机梯子代理)；b64 经 `LocalImageStore` 落 `generated/`(A 方案)。
  - **真实联调（1 张，apinebula gpt-image-2-vip，~¥0.10）**：`/images/edits` 出 1024×1024 有效 PNG(1.28MB)、耗时 115s。
  - 仍属 mock 验证的错误分流(400/429/502/failover 不切备/最贵预留/同模型断言)已全绿；**留给 QA 真实验证**：① 真实 400/422 不切备、429/5xx 切备行为；④图生图换背景质量；以及 composition 接线后端到端。
  - ⚠️ 注：`build_gpt_image_provider` 已就绪但**尚未接进 build_engine 路由**（GPT_IMAGE_2 在 build_engine 里仍是 Mock）。按草案接线是下一步，可另开 issue 或并入本 issue 验证。
- 2026-06-08 [QA] **复验通过关闭**（五项均由本季真实测试覆盖）：①错误切换：实测真实出图错误 `gpt-image-2 401 (不切备)`/`400 (不切备)`/`503`(切备) status_code 分流正确，502 不调 .json()。②预算口径：fallback 后 `CostGuard.reconcile` 回正，ledger 净额=实际成本（ISSUE-0009 已验关闭）。③b64_json→ImageStore：真实出图 b64 解码经 `LocalImageStore` 落 `generated/<sha>.png`，多次真图(花生/listing)。④图生图 `/images/edits`：reference_images 非空走 edit multipart，真实图生图多次成功(保产品换背景准确)。⑤超时：provider 180→300s，实测 edit ~117–247s 在窗口内成功；旧 180s 误触 failover 已修。状态=已关闭。
