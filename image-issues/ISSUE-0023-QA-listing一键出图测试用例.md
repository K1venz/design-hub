---
id: ISSUE-0023
title: QA——listing 一键出图（multipart 直传 + 纯 prompt）测试用例
status: 已确认
severity: P2
reporter: 开发
owner: QA             # 球在 QA：出并执行测试用例
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
