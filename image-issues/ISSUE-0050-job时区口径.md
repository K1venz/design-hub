---
id: ISSUE-0050
title: job 时间戳时区口径待统一（历史/详情时间显示口径）
status: 已确认        # 根因明确+档A口径确认+PM排期已给(P3 slot 排前端波次+0052后)；待 coordinator 到点派 dev 执行→转修复中
severity: P3          # 轻微：显示/口径问题，不影响出图/计费/owner 隔离
reporter: PM          # coordinator #918 收口备忘，PM 入档占位
owner: 开发            # 口径=档A、排期已定、存量行=(a)接受偏移不订正已拍；待 coordinator 到点派工，dev 执行转修复中
created: 2026-07-02
updated: 2026-07-06
related:
  - issue: ISSUE-0048（chat agent 上线收口备忘衍生）
  - 群聊: image-gen#1 #918（收口备忘：job 时区口径 P3 另开小 issue）
---

## 背景
coordinator #918 收口备忘列出「job 时区口径 P3、另开小 issue」。PM 入档占位——**具体根因/范围待 dev 细化**（PM 手头无 job 时间戳时区不一致的复现细节，只知 coordinator 列为 P3 轻微项）。

## 待 dev 明确
- 现象：job（listing_job / generation 时间戳）在何处显示时区口径不一致？（历史列表 / 详情页 created_at / SSE 事件时间？）
- 根因：DB 存储时区（UTC vs 本地）与前端展示时区是否统一？两阶段落库（5af8a04+2f82799）引入的『生成中』行时间戳是否同源？
- 影响面：纯显示口径、不涉计费/owner/出图正确性（故 P3）。

## 根因细化（2026-07-06 dev 代码审计定位）
**根因 = 时间戳生成口径在代码里分叉成两套时钟，且列的 tz 声明在 MySQL 是空头支票。**

1. **生成侧两套时钟并存**（核心）：
   - `created_at`（listing_job / listing_image / chat_session / chat_message 等所有建行）= `server_default=func.now()`。
     MySQL 的 `NOW()` 取 **DB 会话 `time_zone`**；而 `infrastructure/db/session.py:10` 的 `create_async_engine(db_url, pool_pre_ping=True)`
     **没设 `time_zone`/`init_command`** → 用 MySQL 服务器默认 tz（prod 容器多为 `SYSTEM`=宿主本地，很可能 CST/UTC+8）。→ **存的是 DB 服务器墙钟、无 tz**。
   - `completed_at`（`listing_history_repo.py:86/100`）、chat `updated_at`（`chat_repo.py:53`）、ledger（`sqlalchemy_ledger.py:14`）= `datetime.now(UTC)` = **显式 UTC**。
   - → **同一个 job 的 `created_at`（DB 本地）与 `completed_at`（UTC）踩在不同时钟上**：若 prod DB 是 CST，`completed_at` 比 `created_at` 早 8h → 详情页「完成早于创建」/ 时长为负 / 历史「几小时前」离谱。

2. **`DateTime(timezone=True)` 在 MySQL 是 no-op**：MySQL `DATETIME` 不存 tz（只有 `TIMESTAMP` 才 tz-aware，且 aiomysql 仍回 naive）。
   读回一律 **naive datetime**（无 tzinfo），`timezone=True` 声明形同虚设。→ 序列化层（Pydantic `datetime` 字段，`listing_history_schemas.py:17/61/62`、
   `auth_schemas.py:47`）吐出**不带 `Z`/offset** 的 ISO 串（`2026-07-06T10:30:00`），前端 `new Date(...)` 把无 tz 串**按浏览器本地时区**解析 → 若真值是 UTC，UTC+8 用户看到**未来 8h**。

3. **本地测不出**：sqlite（本地/pytest）`func.now()` 出 **UTC**，与 prod MySQL 的 DB-tz **口径不同** → 本地全绿、prod 才现形。这也是它一直只是「收口备忘」没被测试网住的原因。

**影响面**：纯显示口径（历史列表/详情 created_at·completed_at·时长、chat 会话列表 updated_at 倒序的绝对时间展示）。**不涉计费/owner/出图正确性/排序相对次序**（同表内 func.now() 之间相对大小仍单调，故列表倒序本身不乱，只是跨字段/跨表绝对值错位 + 前端本地化误解）→ 维持 P3。

## 修复方案（dev 推荐，待 PM 排期）
**档 A（推荐·彻底·零迁移）「全链 UTC 单一事实源 + 序列化带 Z + 前端本地化」**：
- 把 `created_at` 的生成从 DB 侧 `server_default=func.now()` 收敛到 **app 侧 `datetime.now(UTC)`**（域层/repo 显式赋值，与现有 completed_at/updated_at/ledger 口径拉齐）——消除对 DB 服务器 tz 的隐式依赖，本地 sqlite 与 prod MySQL 从此同口径。
- 序列化层把 naive-UTC 值**显式标 UTC**（Pydantic `field_serializer` 输出带 `Z`），前端 `new Date` 得正确瞬时 → 按用户本地时区渲染。前端展示本地化属 image-web，需 frontend 配合（另条目/随手做）。
- **零迁移可落**：只改 ORM `default` + repo 赋值 + 序列化，**不 alter 已有列、不加列、不改语义**（DDL 的 `server_default` 可保留做兜底，已存量历史行不动）。故**不触 DB 铁律的建表/改 schema 面**——但按保险，排期时请 PM 向用户确认「纯 ORM/序列化层改、零 DDL」这一口径即可，无需重新签 schema。
- 符合「old code adapts to new architecture」：把散落的 `func.now()` 全部收敛进 app 层 UTC 单一事实源。

**档 B（不推荐）「DB 会话钉 UTC」**：engine `connect_args`/`init_command="SET time_zone='+00:00'"` 让 `func.now()` 也出 UTC。改动小，但①仍留「序列化无 Z→前端本地误解」第二坑没治；②sqlite 不吃这套、本地 prod 仍不同源 → 不彻底。

### 存量历史行偏移处置 = (a) 接受旧行偏移、不订正（PM #963 倾向 + coordinator #964 拍板，dev 认可）
- 档 A 后**新行** created_at=app-UTC-naive + 序列化加 `Z` = 全对；**存量旧行** created_at 是当初 DB-local naive 写入，被统一加 `Z` 后会偏移（若 prod=CST 则 +8h、偏到未来）。**接受不订正**——P3 + 内测低量 + 旧行本就时长为负脏态 + (b) backfill 要碰 prod 数据且硬编码偏移量脆弱，为 P3 显示问题吃一次 prod 数据订正风险不划算（YAGNI + 本仓「不主动迁移/订正」铁律）。代价=列内新旧口径混存（旧 CST-naive / 新 UTC-naive）、display-only 容忍，旧脏行随真实使用增长占比自然 →0。
- **⚠️ 前置必做（dev 执行时第一步）：实测 prod DB 实际时区**——`SELECT @@session.time_zone, @@global.time_zone, NOW(), UTC_TIMESTAMP();`。因为**整个 bug 量级与旧行偏移都取决于 prod DB 会话 tz**，方案不假设 CST、实测拍板：
  - 若 **prod DB=CST**（`NOW()` ≠ `UTC_TIMESTAMP()`）：8h 双时钟 bug 真实、旧行 created_at 按 (a) 接受 +8h 已知偏移。
  - 若 **prod DB 本就=UTC**（`NOW()` == `UTC_TIMESTAMP()`）：则 created_at 一直是 UTC-naive、**根本无 8h 双时钟 bug**；档 A 加 `Z` 反把新旧行一起顺带修正（旧行也无偏移）→ 0050 近乎 no-op 收尾。
- **QA 口径**：新行 created_at/completed_at/时长 必须全对（app-UTC+Z、按用户本地渲染）；旧行按实测——prod=CST 则旧行 +8h 标注为**已知可接受、非回归**，prod=UTC 则旧行亦对。**新行/旧行分别验**。

## 处理记录
- 2026-07-02 [PM] coordinator #918 收口备忘入档占位（P3 轻微、非阻断）。root cause + 范围待 dev 细化后转「已确认」。
  owner=开发（时间戳口径归代码侧）。若细化后发现涉迁移/schema=按铁律先报用户签字。
- 2026-07-06 [dev] **根因细化完成**（代码审计，0051 上线后候场窗口内做）：定位=时间戳生成口径分叉（`created_at`
  走 DB 侧 `func.now()`=DB 服务器 tz vs `completed_at`/`updated_at`/ledger 走 app 侧 UTC）+ `DateTime(timezone=True)`
  在 MySQL no-op（读回 naive）+ 序列化无 Z 致前端本地误解；sqlite/MySQL 口径不同故本地测不出。现象=同 job 完成早于创建/
  时长为负、历史绝对时间偏移。**给出修复档 A（全链 UTC 单一事实源、零 DDL 可落）推荐 vs 档 B（DB 钉 UTC，不彻底）**。
  status 待复现→已确认（机制明确）。**球回 PM 排期**（P3 低优，不阻断真实用户）+ 确认「档 A 纯 ORM/序列化层改、零迁移」口径；
  PM 排到即 dev 执行（image-code 内、无 DB DDL、无 撞车）。owner=开发→PM。
- 2026-07-06 [PM] **口径确认 = 档 A + 排期已给**：
  ① **口径拍板档 A**（全链 UTC 单一事实源 + 序列化带 Z）——符合「散落 func.now() 收敛进 app 层单一 UTC 事实源」的干净重构，
     非双时钟妥协。**零 DDL/零迁移=纯 ORM 默认值+序列化层改、不碰建表/改 schema→不触 DB 亲签铁律**（coordinator #961 已拍这条，
     PM 认可：这不是 DB-schema 决策，无需用户签字）。
  ② **排期（PM 权）**：P3 不阻断真实用户，正式 slot **排在「前端优化小波次（记住我修复+忘记密码占位）」+ ISSUE-0052 白底剥离（P2）之后**；
     认可 coordinator #961 时序（改面不小=所有 created_at 调用点，需 QA 回归，别现在插队撞档期）。到点由 coordinator 编排派工，dev 执行时转「修复中」。
  ③ **⚠️ dev 修复设计须处置的暗坑——存量历史 created_at 行偏移**：档 A 后新行 created_at=app-UTC-naive、序列化统一加 `Z`；但**存量历史行的
     created_at 当初是 DB-local(疑 CST) naive 写入的**，被序列化统一标 `Z` 后前端会把旧 CST 值当 UTC 解析 → **旧行 created_at 显示 +8h（偏到未来）**。
     两条出路请 dev 在修复方案里明确二选一：(a) **P3 接受旧行偏移不订正**（内测数据量小、旧行本就已经时长为负的脏态，成本零）；
     (b) **一次性 backfill 数据订正**（`UPDATE ... created_at -= 偏移`，属数据订正非 DDL、但仍碰 prod 数据=须走备份+可回滚+coordinator 编排，
     且偏移量硬编码 CST 脆弱）。**PM 倾向 (a)**（P3+内测+YAGNI，不值一次 prod 数据订正的风险），但把决定权留给 dev 按实际 prod 数据量定，QA 验收时**新行/旧行分别验**。
  owner=开发（口径+排期已定，待 coordinator 到点派）。
- 2026-07-06 [coordinator+PM] **存量历史行处置拍定 = (a) 接受旧行偏移、不订正**（coordinator #964 拍、PM 一致）：
  理由=P3 + 内测低量（prod 真实历史本就少、旧行多为测试脏态且已时长为负）+ (b) backfill 碰 prod 数据+硬编码 CST 偏移脆弱、
  为一个 P3 显示问题吃 prod 数据订正风险不划算（YAGNI + 本仓「不主动迁移/订正」铁律）。→ **档 A 最终 = 只保新行正确（app-UTC+Z），
  旧行不动**；QA 新行/旧行分别验、旧行偏移标注为已知可接受。兜底：若到点 prod 真实行量意外大，再单独重估（默认仍 (a)）。
  三条队列确认：前端小波次 → 0052 → 0050。dev #962 已确认档 A 不插队、created_at 全调用点切 datetime.now(UTC) 改面心里有数、
  带 QA 回归清单交棒。
- 2026-07-06 [dev] **(a) 认可 + 落修复方案技术设计**（修复方案 §存量历史行偏移处置）：认可 (a) 接受旧行偏移不订正。
  补关键前置=**dev 执行第一步先实测 prod DB 会话 tz**（`SELECT @@session.time_zone, NOW(), UTC_TIMESTAMP()`）——因 bug 量级与旧行偏移
  都取决于它：prod=CST 则 8h bug 真实+旧行按 (a) 接 +8h；**prod 若本就=UTC 则根本无双时钟 bug、档 A 加 Z 顺带修新旧行、0050 近 no-op**。
  方案不假设 CST、实测拍板；QA 口径=新行必全对、旧行按实测（CST 则 +8h 标已知可接受非回归）。设计完备封存，待 slot 到点 coordinator 派、dev 执行转「修复中」。owner 保持开发。
