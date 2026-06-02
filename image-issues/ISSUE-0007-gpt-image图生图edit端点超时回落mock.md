---
id: ISSUE-0007
title: gpt-image /images/edits（图生图）真实调用 180s 超时，回落 mock；文生图正常
status: 待验证        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # P0阻断 | P1严重 | P2一般 | P3轻微
reporter: QA
owner: QA             # 两半均已修(fail-fast + 超时300s + 瞬时重试)，待 QA 真实库复验 edit 出图
created: 2026-06-02
updated: 2026-06-02
related:
  - test: image-qa/2026-06-02-e2e-集成验证.md（步骤4）
  - code: image-code/src/design_hub/infrastructure/providers/openai_compat.py（_edit/_request_multipart）
  - code: image-code/src/design_hub/application/pipeline.py（_generate_with_fallback）
---

## 现象
带产品素材的项目出图（图生图，应走 `/images/edits` multipart），真实 gpt-image-2-vip 调用
**恰好 180s 超时**（= provider `timeout=180.0` 上限），抛 `ProviderTimeout` 被 fallback 捕获，
回落到同档备选 seedream-5（mock），最终 `used_model=seedream-5`、`url=mock://…`。
→ **图生图保真主链路当前拿不到真实图**（仅静默降级为 mock）。

对照：**不带素材的文生图**（`/images/generations`）真实调用 **64.5s 成功**，
`used_model=gpt-image-2`、真实 `file://` 落盘 1024×1024 PNG。说明中转站连通/鉴权/模型均正常
（`GET /models` 200/4.0s，`gpt-image-2-vip` 在列），**问题定位在 edit（图生图）请求本身**。

## 复现步骤
1. 真实 MySQL+Redis 起 API（DB_URL/REDIS_URL 指真实库）。
2. 建客户/项目/需求单，上传 1 张产品图 → asset_id。
3. `POST /projects/{id}/generate`，body：`{subscene:S1, family:family_4, tier:standard, category:食品, style:清新自然, width:1024,height:1024, n:1, asset_ids:[asset_id]}`（有素材 → pipeline 走 EDIT）。
4. 观察：约 180s 后返回 200，但 `used_model=seedream-5`、`url=mock://seedream-5/0.png`。

## 期望 vs 实际
- 期望：图生图 edit 真实返回 `used_model=gpt-image-2` + `file://` 真实图（与 text2img 一致，秒级~分钟级）。
- 实际：edit 请求 180s 超时 → 回落 mock，主业务保真链路不可用，且对调用方"成功 200"**静默降级**。

## 环境 / 上下文
- 中转站：apinebula.com/v1，model=gpt-image-2-vip，provider `trust_env=False`（已绕过本机 SOCKS）。
- text2img 同站同模型同 key 64.5s 成功 → 排除连通/鉴权/网络；指向 `/images/edits` 多部分请求
  （疑点：multipart 字段约定 / image 尺寸·mime / 该中转站对 edit 端点的支持或排队）。
- 影响面：PRD 图生图保真为主业务（参 memory「图生图保真靠 /images/edits」），P1。

## 待开发排查方向（建议）
1. 直连 `curl -F` 打中转站 `/images/edits`（短超时）复现，拿原始 HTTP 行为（卡连接？卡响应？4xx？）。
2. 核对 edit multipart 是否需额外字段（如 `response_format`、`image[]` 数组、mask、square/png 限制）。
3. 超时与"静默降级"策略评估：edit 主链路超时是否应直接上抛而非静默回落 mock（避免假成功）。

## 处理记录
- 2026-06-02 [QA] E2E 集成验证发现：edit 真实调用 180s 超时回落 mock，text2img 真实成功。已带证据开单，owner→开发。状态=待复现。
- 2026-06-02 [开发] 拆两半处理：
  **半①「静默降级假成功」已修(本提交)**——违反 fail-fast(不得用 mock 假数据掩盖真实失败)。
  Provider 端口加 `is_live`(真实=True；Mock/占位=False；Failover 取 any)，`GenerationPipeline`
  加 `require_live_for_edit`(默认 False 保 dev/CI 全 Mock 行为；生产 asgi+worker 置 True)。
  EDIT 保真链路下，主模型(真实 gpt)失败后**拒绝降级到非真实 Provider**，改为 fail-fast 抛
  ProviderError→502(并 rollback 预扣)，不再静默返回 mock 假成功。smoke 验证:生产 EDIT gpt 超时→
  拒 mock→抛错+回滚；dev EDIT 仍接受 mock；生产 TEXT2IMG 不受影响。ruff+mypy(160) 绿。
  改动: ports/model_provider.py、providers/mock.py、providers/failover.py、application/pipeline.py、
  interface/api/asgi.py、infrastructure/queue/worker.py。
  **半②「edit 端点 180s 超时真因」未解决**——代码侧审查 multipart 构造(`image` 文件 + model/
  prompt/n/size)符合 OpenAI /images/edits 协议，无明显 bug；180s 恰等 client timeout 说明请求连上
  但中转站不响应，疑中转站 edit 端点排队/弱支持(外部)。需真实 `curl -F` 短超时复现拿原始 HTTP 行为，
  **会产生真实调用费用+耗时，待用户授权预算后再排查**。在此之前保真主链路出图能力仍缺(现至少不再假成功)。
  → 状态=修复中，owner=开发(半②挂起待授权)。
- 2026-06-02 [开发] **用户授权 2 次真实调用排查，半②真因已确诊并修复**：
  · 探针#1(精确复现 multipart)：edit 返回 **200 + 真实 b64_json**，但耗时 **187.0s** > 代码 `timeout=180.0`
    → multipart 没错、端点能用，**纯粹超时设太紧**(文生图~64s，图生图 edit~187s，180s 卡临界点)。
  · 探针#2(走真实 provider 端到端)：edit 在 55s 返回 **500「系统繁忙，请稍后再试」**(traceid…)。
    → 该中转站 edit 端点**又慢(~187s)又不稳(间歇 500 过载)**，2 次调用 1 慢成功/1 过载。
  **修复**：① `OpenAICompatImageProvider` 超时放宽并结构化——`httpx.Timeout(timeout, connect≤15s)`
  (connect 快失败 / read 容忍慢响应)；生产 gpt provider `timeout=300.0`(覆盖 187s+余量)。
  ② 瞬时错误重试——5xx/429("系统繁忙")/超时/传输错(I/O 域，规则允许重试)退避重试，`max_retries`
  默认 0(保 dev/CI)、生产 `max_retries=2`；**4xx 坏请求不重试**(立即抛 DomainError)。
  smoke(MockTransport，0 成本)验证:500→重试→200;busy×2→第3次成功;busy×3 超上限抛;400 不重试;
  默认不重试。ruff+mypy(165) 绿。改动: providers/openai_compat.py、composition.py。
  **残留(非代码可解)**：中转站 edit 端点本身慢且间歇过载是**外部供应商问题**，超时+重试已尽量兜住；
  若实测仍频繁过载，属选型问题(见 ISSUE-0003 中转站选型)，需 Ops/PM 评估换站。
  → 状态=待验证，owner→QA(请用真实库复跑步骤4 edit 出图，确认拿到真实 file:// 图、不再回落 mock)。
