---
id: ISSUE-0056
title: 【P0 生产事故】apinebula 图像 key 失效（401 Invalid token）→ prod 出图中断
status: 修复中        # coordinator 已定位+通知用户处理 apinebula 后台；待用户提供新 key/充值 → coordinator 旋转两处 env 实测恢复
severity: P0          # 生产阻断：prod 出图能力中断（核心功能不可用）；但幸运窗口零真实用户撞上（见时间线）
reporter: coordinator  # 0054/0052 QA 轮 qa 出图卡「生成中」暴露、coordinator 定位（#995）
owner: coordinator    # 运维处置中；关键路径**阻塞在用户 apinebula 后台操作**（余额/换 key）
created: 2026-07-07
updated: 2026-07-07
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

## 连带代码缺陷 → 已开 ISSUE-0055（P1，owner=dev）
provider 对 401 等 4xx 也 5 次重试+退避（违反 fail-fast）→ 用户看「永远生成中」而非即时报错。**本次事故正是被这个掩盖**（qa 僵尸单）。修法=4xx 立即抛不重试 + 配合 0047 fail-closed 落「失败」态。→ 让**下次 key/额度失效时失败得干脆、用户秒知**，而非无声卡死。

## 关联影响：0054/0052 验收 & 部署
- **0054/0052 这波代码无恙**（挂因=key 非新代码）。
- **可先补验的**（无需出图）：响应式三档 / chat #4#5 / 栅格懒加载（frontend-b 自证全绿，coordinator 补验）。
- **待 key 恢复**：ISSUE-0052 白底真图抽验（¥2）+ 部署（零迁移轮）。

## 处理记录
- 2026-07-07 [coordinator] P0 事故通报（#995）：apinebula 图像 key 401 失效→prod 出图断；时间线确认零真实用户撞上；
  已通知用户去 apinebula 后台处理、新 key 到手旋转两处 env 恢复；连带发现 provider 4xx 误重试缺陷（→ISSUE-0055）。
- 2026-07-07 [PM] 入档 P0 事故 + **向用户升级**（关键路径阻塞在用户 apinebula 后台操作：余额/换 key）。开连带缺陷条 ISSUE-0055（P1 owner=dev）。
  owner=coordinator（运维处置中）。**幸运窗口零用户撞上**、但出图核心功能中断=P0，恢复优先级最高、阻塞在用户。恢复后：coordinator 实测出图→补 0052 ¥2 抽验→0054/0052 部署→PM 关账；本条随 key 恢复实测通过后转「已修复」。
