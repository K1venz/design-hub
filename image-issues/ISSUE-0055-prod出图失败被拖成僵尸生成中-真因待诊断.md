---
id: ISSUE-0055
title: 持久性 5xx（上游渠道 500）被当瞬时错重试 5 次耗 8 分钟才报 + 错误文案未人话化（真因已坐实）
status: 已关闭        # 修法已上线(33268d4总重试墙钟+humanize)+prod实弹自证(失败张人话+2分23秒vs8分钟+部分完成不全灭+按成功张计费)
severity: P1          # 非资损，但持久错干等 8 分钟 + 原始 500 报文直吐用户 = fail-fast/体验硬伤
reporter: coordinator  # ISSUE-0056 P0 事故复盘连带发现（coordinator #995），@pm 请开条
owner: —              # 已关闭：(i)总重试墙钟+(ii)文案人话化 prod 实弹坐实
created: 2026-07-07
updated: 2026-07-07
related:
  - issue: ISSUE-0056（P0 apinebula 平台侧事故=本症状暴露源）
  - issue: ISSUE-0047（fail-closed 落「失败」态——复现单正确落败=其已生效；两单僵尸=容器重启孤儿归 0050 reaper）
  - issue: ISSUE-0050（reaper 时区——两单孤儿僵尸 15min 可扫的下游，现 8h 保守）
  - code: image-code infrastructure/providers/openai_compat（_raise_for_status/generate 重试边界·墙钟）、5b53555（4xx fail-fast 已在·2026-06-11 上线）、513ca0b（用户话术层现成）
  - 铁律: fail-fast——4xx 不重试**现网已满足**（dev 证）；本条 = 持久性 5xx 被当瞬时错重试无墙钟 + 错误文案未人话化
  - 群聊: image-gen#1 #995（P0 复盘）、#998（dev 证伪 4xx 误重试）、#999（coordinator 撤回初判 + 真实数据坐实真因）
---

## 症状 & 真因（已坐实，coordinator #999 实证）
key/额度/上游故障场景，出图 job **干等约 8 分钟才报失败** + **原始英文 500 报文直吐用户**。
**真因坐实**（复现单 `852f6176`：15:05 建→8 分钟后落「失败」，error=`gpt-image-2 500: prepare chat requirements error (traceid…)`）：
- **出图端点 `/images/edits` 返 500**（apinebula new-api 上游渠道故障）→ provider 把 500 当**瞬时错走合法 5 次退避**→ 连续同错 5 次、**耗 8 分钟**才 fail-closed 落败。**功能正确（最终落败），但太慢 + 报文难懂**。
- **`4xx 也重试` 初判已撤回**（dev #998 证 + coordinator #999 认）：现网 4xx 早已 fail-fast、绿测锁死；py-spy 见的重试来自 500 非 401。
- **两单僵尸(2ec7/4665) ≠ 本条**：容器重启丢任务的**孤儿**（等 ISSUE-0050 修 reaper 时区后 15min 可扫、现 8h 保守），非重试问题。

## 修复方向（coordinator #999 收窄 + dev #1000 技术修法，原「4xx 不重试」已在不动）
1. **(i) 持久性 5xx 重试总墙钟**（dev 倾向此法，比「同错误体连续 N 次快速失败」更稳=不依赖上游错体格式、天然覆盖持久+瞬时）：
   **根因** = `retry_max_sleep=30` 只封**单次** sleep、**没封总墙钟** → 5 次退避累计 ~8 分钟。**修法** = 加**总重试墙钟预算**（累计 sleep 封顶 ~60–90s，超即穷尽 fail-closed）；落库 error 仍如实、只更快到「失败」。**补测** = mock 连续 500 → 断言总耗时/调用次数被墙钟截断。
2. **(ii) provider 失败错误文案人话化**（同 `513ca0b` 分层）：现 error 原样落 `gpt-image-2 500:{"error":…traceid…}` 直吐用户 → 在 error 落库/呈现处过一层话术映射：**5xx/超时→「图像服务临时繁忙，请稍后重试」**、**4xx 鉴权/配置→「图像服务暂不可用，请稍候」**，均带**「本单未扣费」**；**原始技术错保留进日志、不进用户面**。
3. **(iii) qa 两单孤儿僵尸** = 容器重启丢任务、非重试问题 → coordinator 手工清/等 reaper；**dev 修 ISSUE-0050 reaper 时区口径时一并校准僵尸扫描阈值**（现 8h 保守→时区修正后回 15min），归 0050 域、两条同批。

## 验收标准（QA，修后）
1. **持久 5xx 快速失败**：上游持续 500（可 mock）→ job **秒级/短墙钟内落「失败」**（非干等 8 分钟）。
2. **错误人话**：用户侧看到人话错误（「图像服务临时故障…本单未扣费」）、非原始英文 500/traceid 报文。
3. **瞬态韧性不回退**：真瞬时 429/5xx/网络仍在墙钟内合理重试成功；4xx fail-fast 绿测仍绿（不动已对的点）。
4. 零回归：正常出图路径不变。

## 范围外（YAGNI）
重试策略可配置化框架 / 断路器 / 全 provider 统一重试中间件 / 上游渠道自动切换。

## 处理记录
- 2026-07-07 [PM] coordinator #995 P0 事故复盘连带发现，@pm 请开条 → PM 初次入档（按 coordinator 初判「4xx 误重试」，P1 owner=dev）。
- 2026-07-07 [PM] **根因修正（dev #998 证伪）**：dev 拿代码引用 + 绿测锁死（test_generate_does_not_retry_4xx_business_error）+ git 溯源
  （5b53555·ISSUE-0047·2026-06-11 上线）证 **4xx 早已 fail-fast 不重试** → 采纳 dev 更正，**绝不改一个已经对的点**。本条转「待复现·真因待坐实」三走向。
- 2026-07-07 [PM] **真因坐实（coordinator #999 撤回初判 + 实证）**：复现单 `852f6176` 最终「失败」、error=上游 **500**（apinebula new-api 上游渠道故障）→
  **走向 1 坐实**：持久 5xx 被当瞬时错走合法 5 次退避、8 分钟才报（功能对但太慢 + 报文难懂）；两单僵尸=容器重启孤儿（归 0050 reaper，非重试）；镜像走向排除。
  **修法收窄** = ① 持久 5xx 重试墙钟/同错快速失败 + ② 错误文案人话化（513ca0b 话术层）。status 待复现→**已确认**（真因明确）；owner=开发。
  **排期**：P1 维持、**与 ISSUE-0050 同批**（都 image-code 内、无 DDL；dev 先实测 prod tz 修 0050 顺带清孤儿 reaper）。到点 coordinator 派工、dev 执行转「修复中」。真实用户 bug 随时打断优先。
- 2026-07-07 [dev] **技术修法收窄确认**（#1000，诊断对齐）：(i) 根因=`retry_max_sleep=30` 只封单次 sleep 没封总墙钟→加**总重试墙钟预算**
  （累计 sleep 封顶 ~60–90s 超即穷尽 fail-closed，比「同错体连续 N 次」更稳）+ 补测 mock 连续 500 断言总耗时/调用被截断；(ii) error 落库/呈现处
  话术分层映射（5xx→繁忙请稍后重试 / 4xx→暂不可用，均带「本单未扣费」，原始错进日志不进用户面）；(iii) 孤儿僵尸阈值随 0050 reaper 时区修一并校准（8h→15min）。
  **序**：**不动 0055/0050 代码，先走完当前波次**（key 恢复→0052 白底抽验→0054+0052 部署）再到此批；0050 前置=先实测 prod tz。dev 到点补技术修法+测试。owner=开发（候场待派）。
- 2026-07-07 [dev] **收窄修法实现完成**（commit `9fc98a5`；用户授权「有些能做的先去修改」于部署波次后并行做——纯 image-code、与 image-web/部署不相交）：
  **(i) 总重试墙钟**——`openai_compat` 重试循环加 `retry_max_elapsed`（`settings.gpt_image_retry_max_elapsed` 默认 90s、composition 装配）：
  超总墙钟即穷尽 fail-closed 上抛，持久 5xx 不再干等 max_retries×退避；**只 gate 重试、不砍首次/成功请求**。测=墙钟预算 0 截断持久 500 仅 1 次调用（证墙钟压过 max_retries=5）。
  **(ii) 失败文案人话化**——新 `application/listing/error_messages.humanize_image_error`（SRP）：ProviderTimeout(5xx/429/超时)→「图像服务临时繁忙」/
  裸 DomainError(4xx)→「暂不可用」/ProviderError→「暂时未能出图」/领域错子类透传/未预期兜底；**原始技术错(500/traceid/模型名)进日志、不进用户面**。
  `commands._fail` 落库+发 TASK_FAILED 用人话 + `refunded` 标记（出图段=已回滚/未预扣→附「本单未扣费」、落库段=已计费→不附）；套图分张失败原因(service.generate)同人话化。
  测=分桶+无泄漏单测(test_error_messages) + 命令失败路径测改断言人话+refund 分支。**4xx fail-fast 绿测不动**。ruff+mypy(src) 绿、pytest 106 绿+1 已知 WIP 红。
  status 已确认→待验证；owner→coordinator（QA 验收 ①持久5xx秒/短墙钟内落败 ②人话 ③瞬态韧性不回退+4xx绿 ④零回归 + 编排部署；可与 0050 同批或单独一轮）。
- 2026-07-07 [PM] **排期裁决 = 0055 优先、脱钩 0050、下次部署窗口捎带**（采纳 dev #1004 建议）：
  理由：① 我们正处在 apinebula 平台侧不稳的 P0（ISSUE-0056）里，0055 直接把「下次 key/上游抖动」的用户体验从「干等 8 分钟 + 英文 500 报文」升级为「秒级/短墙钟失败 + 人话『临时繁忙·本单未扣费』」——**对当前这类故障是即时加固**；② 0055 纯 image-code、门禁绿、**QA 可 mock 持续 500 验证=不需真 key/真出图** → **现在即可 QA、独立于 key 恢复**；③ 0050 是 P3 + 需 frontend-b 协调批次（序列化带 Z 前端契约变更），把 P1 的 0055 压在 P3 协调批次后不合理。
  → **0055 走独立 QA + 独立/捎带部署**（不等 0050）；QA 可即跑（mock），部署窗口由 coordinator 编排（可趁 key 恢复部署一并、或更早独立上以改善当前故障 UX）。owner=coordinator。真实用户 bug 仍最高优先。
- 2026-07-07 [coordinator] **单发上线 prod**（#1005，采纳 PM 优先排期）：commit `33268d4` 波、回滚镜像 `rollback-20260707-160112`、smoke 绿；
  核关键 diff（墙钟只 gate 重试 + sleep 钳到剩余预算 / humanize 分层、原始错留日志）+ targeted 8 绿 + 全量 106 绿（1 known WIP red）。
  **待验证保持**：真验收 = key 恢复后 coordinator 在 prod 打一单看实弹（快速失败 + 人话文案），**与 ISSUE-0052 ¥2 抽验同批收口** → 一并交 PM 关。
- 2026-07-07 [PM] **关账批次登记**：0055 已上线 prod（33268d4），待验证保持。**关账 gate = key 恢复后 prod 实弹一单**（持久故障场景秒级/短墙钟落败 + 人话「临时繁忙·本单未扣费」）。
  与 **ISSUE-0052（白底 ¥2 抽验）+ ISSUE-0056（事故恢复实测）同批收口**：key 恢复 → coordinator prod 一轮（0052 抽验 + 0055 实弹 + 出图恢复确认）→ PM 一并关 0052 + 0055 + 0056。owner=coordinator。
- 2026-07-08 [coordinator+PM] **✅ prod 实弹自证、关账（#1094）**：出图恢复后新 key 分组限流紧、出现失败张 → **意外成为 0055 的线上实弹自证**：
  ① **(ii) 文案人话化坐实**：失败张显示「图像服务临时繁忙，请稍后重试」（非原始英文 500）；② **(i) 总重试墙钟坐实**：整单 **2 分 23 秒**落定（对比事故时 8 分钟）；③ **部分完成不全灭 + 按成功张计费**（fail-closed 分层正确）。(i)(ii) 全线上坐实。**PM 关账**：修法 `33268d4` 已上线 + prod 实弹三点自证 → status→**已关闭**。（注：limit 更紧的限流本身=新观察 ISSUE-0063、非本条缺陷；本条=「失败得干脆+人话」已达成。）
