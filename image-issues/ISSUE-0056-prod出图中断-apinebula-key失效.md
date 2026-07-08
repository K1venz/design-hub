---
id: ISSUE-0056
title: 【P0 生产事故】apinebula 图像 key 失效（401 Invalid token）→ prod 出图中断
status: 已关闭        # 出图恢复实证(用户提供gpt-image-2-1k分组新令牌×2→coordinator旋转prod/qa env→prod两单5张成功¥2.0)；事故闭环
severity: P0          # 生产阻断：prod 出图能力中断（核心功能不可用）；但幸运窗口零真实用户撞上（见时间线）
reporter: coordinator  # 0054/0052 QA 轮 qa 出图卡「生成中」暴露、coordinator 定位（#995）
owner: —              # 已关闭：根因=令牌分组、解法=新分组令牌+旋转env、prod出图恢复实证
created: 2026-07-07
updated: 2026-07-08
related:
  - issue: ISSUE-0055（连带代码缺陷：provider 对 4xx 也重试→掩盖成「永远生成中」，P1 owner=dev）
  - issue: ISSUE-0047（套图失败落地=fail-closed 下游配合）
  - project: 图像中转站选型（apinebula=gpt-image 中转，唯一 live 图像 provider）
  - 群聊: image-gen#1 #995（事故通报）
---

## 事故（coordinator #995）
**apinebula 图像 key 失效（401 Invalid token）→ prod 出图已断**（qa/prod 同一把 key 双 401）。图像出图是核心功能，key 失效 = 出图能力全断 = **P0 生产阻断**。

## 时间线 & 影响面
- **最后成功出图单**：07-06 14:55（admin）。
- **真实用户 2665867188**：昨天 14:07–14:34 三单**全部成功**（key 失效前）。
- 此后 prod **无任何新出图单** → **零真实用户撞上 401**（幸运窗口）。
- **发现路径**：0054/0052 QA 轮 qa 出图 job 卡「生成中」→ py-spy + 直测中转站 → qa/prod 同 key 双 401。

## 处置（coordinator 运维，进行中）
- ✅ 已定位（key 失效、非新代码问题——0054/0052 这波代码本身无恙）。
- ✅ **已通知用户去 apinebula 后台处理**（查余额 / 换 key）。
- ⏳ **关键路径阻塞在用户**：需用户在 apinebula 后台充值或换新 key。
- ⏳ 新 key 到手 → coordinator **旋转两处 env**（qa + prod）并实测恢复出图。

## 🔴 待用户操作（PM 升级）
**去 apinebula 中转站后台**：① 查图像 key 余额/状态；② 若余额耗尽→充值，或→生成新 key。新 key 交 coordinator（**不进群聊明文**，走安全渠道）→ coordinator 旋转 env 恢复。

## ✅ 事故根因坐实（coordinator #999 撤回初判 + 实证；dev #998 反证成立）
- **根因 = apinebula 平台侧不稳**：复现单 `852f6176`（15:05 建）实测 error=`gpt-image-2 500: prepare chat requirements error (traceid…)`——出图端点 `/images/edits` 返 **500**（new-api **上游渠道故障**）；此后直探同端点漂移成 **401 Invalid token**（中转站侧状态漂移中）。→ **非我们代码、非 key 配置错误**，是中转站/上游渠道波动。
- **我们的代码其实是对的**：复现单走了合法 5 次退避后**正确 fail-closed 落「失败」**（非无限「生成中」）；ISSUE-0047 fail-closed 已生效。
- **两单 qa 僵尸(2ec7/4665) = 容器重启丢任务的孤儿**（非重试、非本事故的直接产物）→ 归 ISSUE-0050 reaper 域（现 8h 保守、时区修后 15min 可扫）。
- **初判「4xx 被重试/永远生成中」已撤回**（见 ISSUE-0055 根因修正史）。

## 连带代码缺陷 → ISSUE-0055（P1，owner=dev，真因已坐实）
真因坐实后收窄为两点（非「4xx 不重试」——那早已在）：**(i) 持久性 5xx 无总重试墙钟**（500 连续退避 8 分钟才报，用户干等）；**(ii) provider 失败错误文案未人话化**（原始 500/traceid 直吐用户）。修法=总墙钟预算 fail-closed + 话术分层（带「本单未扣费」）。**与 ISSUE-0050 同批排**，先走完当前波次（key 恢复→0052 抽验→0054+0052 部署）再动。

## 关联影响：0054/0052 验收 & 部署
- **0054/0052 这波代码无恙**（挂因=key 非新代码）。
- **可先补验的**（无需出图）：响应式三档 / chat #4#5 / 栅格懒加载（frontend-b 自证全绿，coordinator 补验）。
- **待 key 恢复**：ISSUE-0052 白底真图抽验（¥2）+ 部署（零迁移轮）。

## 处理记录
- 2026-07-07 [coordinator] P0 事故通报（#995）：apinebula 图像 key 401 失效→prod 出图断；时间线确认零真实用户撞上；
  已通知用户去 apinebula 后台处理、新 key 到手旋转两处 env 恢复；连带发现 provider 4xx 误重试缺陷（→ISSUE-0055）。
- 2026-07-07 [PM] 入档 P0 事故 + **向用户升级**（关键路径阻塞在用户 apinebula 后台操作：余额/换 key）。开连带缺陷条 ISSUE-0055（P1 owner=dev）。
  owner=coordinator（运维处置中）。**幸运窗口零用户撞上**、但出图核心功能中断=P0，恢复优先级最高、阻塞在用户。恢复后：coordinator 实测出图→补 0052 ¥2 抽验→0054/0052 部署→PM 关账；本条随 key 恢复实测通过后转「已修复」。
- 2026-07-07 [PM] **事故根因坐实修正**（coordinator #999 实证 + dev #998/#1000 对齐）：复现单 852f6176 实测上游 **500**（apinebula new-api 上游渠道故障、后漂移成 401）→
  **根因=apinebula 平台侧不稳、非我们代码/非 key 配置错**；我们代码正确 fail-closed 落败（0047 已生效），两单僵尸=容器重启孤儿（归 0050）。初判「4xx 被重试/永远生成中」撤回。
  连带缺陷 ISSUE-0055 收窄=持久 5xx 无总重试墙钟 + 错误文案未人话化（非「4xx 不重试」）。**用户动作不变**：apinebula 后台核**余额/渠道/key**（现 /images/edits 返 401、需用户处理）。恢复路径不变。
- 2026-07-08 [coordinator] **401 根因文档实锤（用户给 apinebula 官方文档）**：apinebula 把 gpt-image-2 归入「**gpt-image-2-1k 令牌分组**」→ 旧令牌不在新分组=Invalid token（非余额/非代码）。**解法=用户控制台新建 gpt-image-2-1k 分组令牌**。
- 2026-07-08 [coordinator+PM] **✅ 出图恢复实证、事故闭环关账（#1094）**：用户提供 gpt-image-2-1k 分组新令牌×2 → coordinator 旋转 prod=KeyA/qa=KeyB → **prod 真图两单共 5 张成功出图**（新 key 生效、¥2.0 恰在预算）。**PM 关账**：P0 生产事故全程闭环——根因（令牌分组）坐实 + 解法（新分组令牌+旋转 env）+ prod 出图恢复实证；**幸运窗口零真实用户撞上**。status→**已关闭**。⚠️ **遗留观察**（非本条、另 ISSUE-0063）：新 key 分组限流比旧紧（并发 3→2/5 失败、已调 LISTING_CONCURRENCY=1 串行）；升级选项=image2-vip 分组待用户拍。
