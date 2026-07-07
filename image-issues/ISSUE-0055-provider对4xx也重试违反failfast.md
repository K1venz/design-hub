---
id: ISSUE-0055
title: provider 对 401/4xx 业务错误也进 5 次重试+退避——违反 fail-fast，key 失效时用户看到「永远生成中」
status: 已确认        # coordinator #995 事故复盘定位（py-spy+直测中转站坐实），机制明确；待 PM 排期→dev 修
severity: P1          # 非资损，但掩盖故障=用户体验硬伤（key 失效时无限「生成中」而非明确报错），fail-fast 铁律违反
reporter: coordinator  # ISSUE-0056 P0 事故复盘连带发现（coordinator #995），@pm 请开条
owner: 开发            # 修法方向明确（4xx 立即抛不重试）；待 PM 排期，dev 可与 0050 一起排
created: 2026-07-07
updated: 2026-07-07
related:
  - issue: ISSUE-0056（P0 apinebula key 失效事故=本缺陷暴露源）
  - issue: ISSUE-0047（套图并发/失败落地——fail-closed 落「失败」态是本修的下游配合）
  - code: image-code infrastructure/providers/openai_compat（图像 provider 重试退避逻辑）、513ca0b（用户话术层现成）
  - 铁律: fail-fast——非 I/O/网络类错误不重试；4xx 业务错误属确定性失败、重试无意义
  - 群聊: image-gen#1 #995（P0 事故复盘连带发现）
---

## 定性（ISSUE-0056 事故复盘连带发现，coordinator #995）
apinebula 图像 key 失效（401 Invalid token）时，图像 provider 对 **401 这类业务 4xx 也进 5 次重试 + 指数退避**——违反 fail-fast 铁律（**4xx 确定性失败不该重试**）。后果 = key 失效时用户看到「**永远生成中**」而非**立刻明确报错**（本次 P0 事故 qa 两单僵尸「生成中」+ coordinator 复现单皆此症）。

## 根因
`openai_compat` provider 的重试退避对**所有非 2xx 一视同仁**进退避重试，未区分：
- **4xx 业务错误（401/403/400 等）= 确定性失败**：key 无效/参数非法，重试 5 次结果一样，只是把「即时失败」拖成「退避 5 轮后才失败」→ 上层看起来长时间卡住。
- **429 / 5xx / 网络类 = 瞬态失败**：重试退避才有意义（I/O/网络域，铁律允许）。

## 修复方向（coordinator #995 给，待 dev 落）
- **openai_compat 对 4xx（401/403/400）立即抛、不重试**；**只 429 / 5xx / 网络类进退避**（fail-fast 铁律：确定性错误不重试、仅 I/O 瞬态重试）。
- **配合 ISSUE-0047 fail-closed**：出图失败即落「**失败**」态（非无限「生成中」）+ 错误信息人话（**话术层 513ca0b 现成**，chat/工作台复用）。
- 语义边界：只改「哪些错误值得重试」，不改校验/业务语义。

## 验收标准（QA，修后）
1. **4xx 不重试即时失败**：provider 遇 401/403/400 立即抛（不进 5 轮退避）；job 迅速落「失败」态、错误信息人话（非无限「生成中」）。
2. **瞬态仍重试**：429 / 5xx / 网络类仍走退避重试（I/O 韧性不回退）。
3. **端到端**：key 失效场景（可 mock 401）→ 用户侧秒级明确报错、无僵尸「生成中」。
4. 零回归：正常出图/既有重试成功路径不变。

## 范围外（YAGNI）
重试策略可配置化框架 / 断路器 / 全 provider 统一重试中间件（本条只修 4xx 误重试这一确定性 bug）。

## 处理记录
- 2026-07-07 [PM] coordinator #995 P0 事故（ISSUE-0056 apinebula key 失效）复盘连带发现，@pm 请开条 → PM 入档：
  定级 **P1**（非资损，但掩盖故障=fail-fast 铁律违反、用户看无限「生成中」是体验硬伤）。根因=provider 对 4xx 业务错误也退避重试、未区分确定性失败 vs 瞬态。
  修法=4xx 立即抛不重试、只 429/5xx/网络进退避 + 配合 0047 fail-closed 落「失败」+ 513ca0b 话术。owner=dev。
  **排期**：P1 但非阻断当前（P0 事故本身走 key 旋转恢复=ISSUE-0056；本条是让「下次 key/4xx 失效时失败得干脆」的加固）→ **建议 dev 与 ISSUE-0050 同批排**（都 image-code 内、无 DB DDL、coordinator #995 亦倾向）。到点 coordinator 派工，dev 执行转「修复中」。真实用户 bug 仍随时打断优先。
