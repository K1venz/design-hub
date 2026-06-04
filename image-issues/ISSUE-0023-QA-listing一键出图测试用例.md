---
id: ISSUE-0023
title: QA——listing 一键出图（multipart 直传 + 纯 prompt）测试用例
status: 已修复
severity: P2
reporter: 开发
owner: PM             # 两步流用例改版+真服务器执行+真实e2e 全过；统计验收(§3.12.6 可用率/P95)需 PM 定采样
created: 2026-06-04
updated: 2026-06-04
related:
  - code: image-code/docs/superpowers/specs/2026-06-04-listing-image-generation-design.md
  - code: image-code/docs/superpowers/plans/2026-06-04-listing-image-generation.md
  - code: image-code/src/design_hub/interface/api/routes/listing.py
  - issue: ISSUE-0021（PM 出验收口径）
---

## 背景
后端 listing 一键出图链路已实现（main 提交 b8ebfc4→ff4593c）：
`POST /listing/generate`(multipart, Bearer) + `GET /listing/{job_id}/events`(SSE)。
轻量链路：multipart 直传 ≤3 图 + 自由 prompt + modifiers(平台/地区/语言) + ratio + n(1..7)
→ 服务端组装 prompt → gpt-image-2 直 edit → 异步出 N 张候选。**Dev 角色不写测试，归 QA 出用例。**

> 本项目无 pytest/测试套件——QA 需先确定测试运行方式（引入 pytest 属基础设施决策，请与 PM/用户对齐再做，不要 Dev 端擅自加）。

## 需 QA 覆盖的用例
**入参/边界（边界即 fail-fast，期望 4xx，不降级）：**
1. 1 / 2 / 3 张图 + 合法 modifiers → 入队返回 `{job_id}`。
2. 0 张 或 >3 张 → 400。
3. `n` 越界（0、8、负数）→ 400；`n`=1..7 合法。
4. `modifiers` 非法 JSON → 400；非对象（数组/标量）→ 400。
5. 未知下拉值（platform/region/language 不在话术表）→ 4xx（fail-fast）。
6. 不支持的 `ratio` → 4xx。
7. 未带 Bearer → 401；SSE 未带 `?access_token=` → 401。

**SSE 进度全序列：**
8. `task_started → model_called → image_generated × n → task_completed`，逐张到达。
9. 出图失败 → `task_failed`（错误显式，不静默吞）。
10. 晚订阅不丢事件（订阅时回放历史，与 ISSUE-0010 同口径）。

**业务正确性：**
11. 最终 prompt 含用户自由文本 + 各 modifier 话术片段（拼接顺序/分隔符）。
12. ratio→size 映射正确（1:1→1024²、9:16→1024×1536、16:9→1536×1024）。
13. 成本：CostGuard 预扣 → 按实回正；provider 失败时预扣回滚（额度不漏）。

**真实联调（带 key 环境，与 Dev/运维配合，见 plan Task 5.3）：**
14. 真实 gpt-image-2 多图 edit（image[] 多字段）是否被中转站支持；不支持时 Dev 退化为并发逐图（验证退化路径与契约不变）。

## 依赖
- 验收口径（成功率/时延/成本红线）待 PM（ISSUE-0021）给出后细化阈值。
- 下拉枚举以 ISSUE-0021 用户确认版为准；话术片段正式文案见 ISSUE-0022（image-prompt）。

## 处理记录
- 2026-06-04 [开发] listing 后端 MVP 完成，创建本条派 QA。状态=已确认，owner=QA
- 2026-06-04 [QA] 测试用例已出并执行（Mock，零成本），报告见 image-qa/2026-06-04-listing-一键出图测试报告.md，
  脚本 listing_test_unit.py / listing_test_http.py。
  · **测试方式决策**：未引入 pytest（基础设施变更需 PM 对齐，不擅自加）；沿用 image-qa 既有风格——
    纯逻辑层直接 import 跑（无 DB）、HTTP/SSE 用 httpx ASGITransport in-process + Mock provider + token 直 mint（无 DB）。
  · **结果**：Layer1 单元 22/22 全过；Layer2 HTTP/SSE 12/16。业务逻辑(prompt 组装/ratio→size/成本预扣回正回滚)、
    SSE 全序列逐张/晚订阅回放/provider 失败 task_failed、鉴权 401 —— 均✅。
  · **发现 1 个真实 bug → 开 ISSUE-0024(P2, owner=开发)**：边界校验未 fail-fast（n/ratio/未知下拉/空prompt 返
    200+job_id 而非 4xx，违反 spec §4.1/§7）；附带错误码 409/422≠spec 的 400、sizing 多接受 4:3 两处小不一致。
  · **用例 14（真实多图 edit）待受控环境**：需 GPT_IMAGE_* key + MySQL + 花钱，与 Dev/运维协调（plan §5.3），本轮未跑。
  · 状态→待验证，owner=QA（持单待 ISSUE-0024 修复回归 + 真实 e2e）。
- 2026-06-04 [QA] **用例14 真实 e2e（单图）已跑通**（受控，真花钱 ¥1.19）：本地起含 listing 的当前代码后端(:8002,
  真实 GPT+MySQL)，`POST /listing/generate`(1 图 + 平台=亚马逊/地区=美国/语言=英文 + ratio=3:4 + 卖点 prompt) → job_id →
  SSE `task_started→model_called(gpt-image-2,163s)→image_generated→task_completed(¥1.19)` → 真实出图
  generated/d8af06ef5d55f111.png（PNG 1024×1536，3:4 映射正确）。出图正确应用 modifier：包装/卖点译为英文、
  排亚马逊 listing 风格、喜庆年货氛围。脚本 image-qa/listing_real_e2e.py。
  · **仍待覆盖**：多图 image[]≥2 的真实 edit（用例14 原意：中转站是否支持多 image 字段、不支持时退化为并发逐图）——本次仅 1 图，多图待后续受控跑。
- 2026-06-04 [PM] ⚠️ **契约变更（ISSUE-0026）需用例改版**：用户拍板 listing 改「先上传预览 → 再出图」，
  multipart 直传被取代为两步：`POST /uploads`（拿 id + 预览）→ `POST /listing/generate` 带 `upload_ids`。
  用例需改版为**两步流**重测：① 新增上传端点用例（大小>10MB/格式非白名单 → 4xx；`GET /uploads/{id}` 预览返图）；
  ② 出图入参从 multipart files → `upload_ids`（数量 0/>3 → 400；id 不存在 → 4xx）；③ 原 SSE 逐张/成本/鉴权用例不变。
  已花钱的单图 e2e 结论（1024×1536 可出图、¥1.19）仍有效，改版后用 upload_ids 复跑一次确认即可。契约见 PRD §3.12.8 + ISSUE-0026。owner=QA。
- 2026-06-04 [QA] **两步流改版完成 + 全套零 mock 验收（用户要求不 mock）**。报告 image-qa/2026-06-04-listing-一键出图测试报告.md §8。
  · **边界/契约：打真服务器 :8002（真路由+真 provider+真鉴权+真落盘，无 mock）21/21 全过**（脚本 listing_real_boundary.py）——
    上传(大小/格式/空/鉴权/预览/404/非法id)、出图入参(upload_ids 0/>3→400、不存在→404、非法格式→400)、
    ISSUE-0024 回归(n/ratio/空prompt/未知下拉→全 400、错误码 400、4:3 已删)、鉴权 401。非法入参边界全 fail-fast，未出图零成本。
  · **真实 e2e（真 gpt-image，n=1，共 ¥2.38）**：C 单图两步流 upload→upload_ids→SSE→真图 1024×1536(116s)；
    D 双图 upload_ids[2]→真图(312s)。SSE happy 全序列真实覆盖。脚本 listing_real_e2e.py。
  · **ISSUE-0024 已修复并回归通过 → 已关闭**；**4:3 超集已删**。
  · **多图 image[]≥2**：上游 apinebula 接受、未失败（详见 ISSUE-0025 残留①；视觉确证待差异化输入）。
  · **残留（非 QA 功能项）**：验收口径 §3.12.6 的「首次可用率 50–60% / P95≤5min」需多样本真实出图采样（成本）+ PM 定口径——
    本轮只验「非法入参全 4xx」✅，统计阈值未跑。状态→已修复，owner→PM（统计验收 + 最终关闭）。
