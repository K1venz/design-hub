---
id: ISSUE-0047
title: 套图只出 1 张（真实用户#1）— apikey 轮换后新 key 分组并发档低，5 路并发打满 429
status: 待验证        # fix 5b53555 已上线 prod（2026-07-02 大批次，smoke 绿）；待 QA prod 复测确认真实流量套图稳定全出
severity: P1          # 旗舰功能(套图=北极星需求#1)对真实用户严重降级：请求 5 张实得 1 张；无资损(成本 reconcile 只计成功张)、非全站阻断，故 P1 非 P0
reporter: dev         # 真实用户#1 反馈，dev 读码坐实根因
owner: QA             # fix 已上线 prod（5b53555）；待 QA prod 复测（真实流量套图稳定全出）
created: 2026-06-15
updated: 2026-06-15
related:
  - code: image-code provider 并发/重试层（套图 plan 展开后 asyncio.gather 多路 n=1 并发调用，单 key 限流敏感）
  - issue: ISSUE-0045（同一 provider 出图链；本 bug 由 apikey 轮换触发、与 0045 张数核无关）
  - 群聊: image-gen#1 #815-#826（apikey 轮换）/ #852（dev 报本 bug + 根因）
  - 背景: 这是项目交付美工实际使用后的**首个真实用户 bug**（真实用户#1）
---

## 现象（真实用户#1 反馈）
真实用户跑套图（默认 plan 1/2/2 = 5 张），**实际只出 1 张**——旗舰功能对真实用户严重降级。

## 根因（dev 读码坐实，#852）
**2026-06-15 apikey 轮换后**（ISSUE 群 #815-#826，换上 apinebula 新双 key），新 key 的中转站**分组并发档位低**；
套图把 plan 展开成多个 task、`asyncio.gather` **一次全并发**多路 `provider.generate(n=1)`（沿用单图并发模型），
5 路并发**打满中转站限流 → 429**，多数张失败、只 1 张成功落图。
即「部分失败」语义在真实流量下被并发限流放大成「几乎全失败」。

## 影响
- 旗舰功能（套图 = toC 北极星需求#1）真实用户体验破——付费预期 5 张、实得 1 张。
- **无资损**：成本守卫 reconcile「只计成功张」（部分失败范式，沿 ISSUE-0030），用户不会被多扣。
- 单图流（n=1 单路）不受影响；其他功能正常。

## 修复方案（dev 已想透，代码暂未动 #852）
I/O 域优雅降级（符合错误处理规则——降级仅允 I/O 域）：
1. **降并发**：把套图并发从「一次全并发」降到**可配置的保守值**（分批/并发窗口），避开单 key 限流档。
2. **重试加 jitter 错峰**：429 重试时加抖动，避免同时重发再次撞限流。
3. **加大重试余量**：给瞬时 429 更多重试预算（I/O 域重试合规）。

## 为何 dev 暂未改（#852）
prod 是**真实用户在用**，碰 prod 改动守纪律——dev 等用户「继续」/明确放行，
再走「改 → QA 验（qa 先行）→ ops 带备份部署 → prod 复测」稳路。**非安全/非 DB**，按既定纪律
coordinator 可代放行（碰 prod 出精确变更计划→确认→apply）；但因真实用户在用，建议用户知会一声。

## 验收标准（QA，dev 修后）
1. 套图默认 1/2/2 = 5 张：真实流量下**5 张全出**（或部分失败时按部分失败范式正确标注+只计成功张），
   不再「只出 1 张」。
2. 并发降档/错峰后单 key 限流不再被打满（多次连跑套图无大面积 429）。
3. 单图流 + 复刻 + 二次编辑无回归。
4. prod 复测（真实用户场景）套图正常出整套。

## 处理记录
- 2026-06-15 [开发] 真实用户#1 报「套图只出 1 张」→ dev 读码坐实根因 = apikey 轮换后新 key 分组并发档低、
  5 路并发打满 429；修复方案已想透（降并发可配置 + 重试 jitter 错峰 + 加大重试余量），**代码暂未动**
  （prod 真实用户在用、等用户「继续」再走改→QA 验→ops 带备份部署稳路）。无资损（reconcile 只计成功张）。
- 2026-06-15 [PM] 交付美工后**首个真实用户 bug**，PM 分诊归档（承 #839 真实用户保障姿态）：定级 **P1**
  （旗舰功能真实用户严重降级、但无资损非全站阻断）。owner=开发（根因已坐实+方案已想透）。status=已确认。
- 2026-06-15 [coordinator] **代放行修复**（#858/#862，按真实用户保障安全流——非安全非 DB、PM/coordinator
  权限内自主放行、用户已给停拦权）；**优先级置于完全复刻改版之上**（本 bug live 坏着、真实用户在撞）。
  路径：dev 改（降并发可配置 + 重试 jitter 错峰 + 加余量）→ QA qa 验 → ops 带备份部署 → prod 复测 → 关。
  QA #861 验收设计：**不一遍 5/5 就放行**——跑多遍压并发（默认 5 张 + 更大 plan 8~10、连跑 3~5 遍）证降并发后稳定全出，
  断言 ① 请求 N 张出全 N ② IMAGE_FAILED=0 ③ cost=请求张数×单价（间歇性 429 不能单遍绿放行）。status→修复中。
  **若 fix 碰 DB/资损面 dev STOP 报 coordinator**（预计纯并发参数、无 schema 无迁移、deploy.sh 迁移 no-op）。
- 2026-07-02 [coordinator/开发] **fix 已上线 prod（commit `5b53555`）**：`listing_concurrency` 默认 3 可配（从「一次全并发」降到保守值）+ provider 指数退避 + equal-jitter + retries 2→5（避 429 撞限流、重试错峰）。随同批大批次上线（工作台「最近一单」恢复 ed79ecd+a8f01df / **两阶段落库** 5af8a04+2f82799：入队即落『生成中』行+逐张增量+失败张留痕+fail-closed+reaper，commands.py 重构为模板方法基类 / auth 打磨 e36f311）。部署 2026-07-02、prod smoke 绿。**纯并发参数+I/O 退避、无 schema 无迁移**（deploy.sh 迁移 no-op）。status→**待验证**、owner→QA。
- 2026-07-02 [PM] 黑板同步（承 #877 coordinator 纠偏——本 bug 在 dev 休眠期已由子 agent 链修复上线，PM 之前记的「修复中·待用户放行」为旧态）：更新 status→待验证、owner→QA、补 fix commit `5b53555` + 部署记录。**QA 复测口径（#861/#863 已定，务必守）**：间歇性 429 **不一遍 5/5 就放行**——跑多遍压并发（默认 5 + 大 plan 8~10、连跑 3~5 遍）证降并发后稳定全出（请求 N 张出全 N / IMAGE_FAILED=0 / cost=N×单价）。QA prod 复测绿 → PM 终验收关闭。
- 2026-07-02 [coordinator] **修复已实现并上线 prod**（子 agent 链，按用户"默认子 agent"编排）：
  ① fix `5b53555`——根因实锤 = listing_service 并发度写死 `_CONCURRENCY=5` + provider 线性退避无抖动齐步重发；
  改为 settings `listing_concurrency`(默认 3、`.env` 可下调至 2 免改码) + provider 指数退避 equal-jitter
  (`gpt_image_max_retries` 2→5、`retry_max_sleep=30s`)，仅 429/超时/5xx/瞬时网络错重试（业务 4xx 仍 fail-fast）。
  8 条新单测（并发不越界/单图恒 1 路/重试语义），pytest 68 绿。
  ② 顺带随两阶段落库(`5af8a04`+`2f82799`)同批部署：套图**失败张现在落库留痕**、僵尸「生成中」单有
  fail-closed 兜底 + 启动 reaper。
  ③ 部署：push.sh + deploy.sh（备份 db-backup-20260702-110604.sql、回滚镜像 rollback-20260702-110427、
  无迁移）；prod smoke 单图 ¥0.4 全链绿（出图中详情 200/status=生成中 → 终态完成/1图/计费对）。
  **status→待验证**：真 429 只能真出图压测验——待跑 `image-qa/taotu_concurrency_verify.py` 多遍压并发
  （QA #861 验收口径：大 plan 8~10、连跑 3~5 遍、出全 N/IMAGE_FAILED=0/cost 对），及用户/美工真实使用复测。
  若默认并发 3 仍偶发 429：ops 在 prod `.env` 设 `LISTING_CONCURRENCY=2` 后 force-recreate api 即可（无需重部署）。
