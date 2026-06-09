---
id: ISSUE-0039
title: 旧流(generation/async_generation/brief)用可伪造 X-User-Id header 做 cost/job 归属，非 Bearer 身份
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P2          # 需登录才能利用 + 主线 listing 已安全;若旧流在 prod 活跃使用且涉真实计费可升 P1
reporter: 开发
owner: PM             # 球在 PM:跨多旧流 refactor 需排期 + 确认旧流是否仍在 prod 暴露使用
created: 2026-06-09
updated: 2026-06-09
related:
  - code: image-code/src/design_hub/interface/api/deps.py:73（UserIdDep = Header("X-User-Id")）
  - code: image-code/src/design_hub/interface/api/routes/generation.py:17,28（user_id=UserIdDep 默认 designer-anon）
  - code: image-code/src/design_hub/interface/api/routes/async_generation.py:46（同上，海报异步流）
  - code: image-code/src/design_hub/interface/api/routes/brief.py:72（同上）
  - code: image-code/src/design_hub/interface/api/routes/listing.py:39（已修对：Bearer 身份即 user_id，不用可伪造 X-User-Id）
  - issue: ISSUE-0006-WP-G（全量挂鉴权前提）
  - 触发: 运维清 cost_ledger 时撞到 user_id 有非数字值 designer-anon（2026-06-09 群聊 #274）
---

## 现象
`cost_ledger.user_id` 里存在非数字值 `designer-anon`（运维清理时撞到）。读码定位：
**海报/旧出图流**（generation 同步出图、async_generation 海报异步、brief 需求单）的 job/cost
`user_id` **取自可伪造的 `X-User-Id` HTTP header（默认 `designer-anon`）**，而不是已鉴权的 Bearer 身份。

## 根因（读码）
- `deps.py:73` `UserIdDep = Annotated[str, Header(alias="X-User-Id")]` —— 客户端可控的请求头，缺省 `"designer-anon"`。
- 这些 handler **验了登录但没用验过的身份做归属**：
  - generation.router / brief.router 挂了 `login_required`（asgi:217/227）；
  - async_generation `POST /async` handler 自带 `_user: CurrentUserDep`（asgi:219 路由级未挂，handler 级有）。
  - 但三者落 job/cost 用的都是 `user_id: UserIdDep = "designer-anon"`（header），**`_user`/login 只验"登录了"、不参与归属**。
- 对照：**listing 已修对**（`listing.py:39` 注释明示「Bearer；身份即落库/历史/成本的 user_id，不用可伪造的 X-User-Id」，用 `CurrentUserDep`）。旧流未迁移。

## 影响
- **成本归属错**：不传 `X-User-Id` → 真实出图成本计到 `designer-anon`，不归本人（cost_ledger/预算守门失真）。
- **越权归属**：传他人 `X-User-Id` → 把自己的 job/成本算到别人头上（或反向），污染他人 job 历史/成本。
- 需「已登录」才能利用（不是匿名滥用）；**listing 主线不受影响**（已用 Bearer 身份）。
- 受影响范围 = 海报/项目旧流（generation / async_generation / brief；projects/selection/export/revision 经查未用 UserIdDep 做 user_id，待逐一复核）。

## 不是这个问题（已排除）
- **app 查 cost_ledger 不会撞 MySQL 1292**：ledger 仓储 `user_id: str`、`CostLedgerEntry.user_id == <str>` 全字符串绑定（`sqlalchemy_ledger.py`、`cost_query.py`、`listing_query_repo.py` 均如此）。运维撞到的 `1292 Truncated DOUBLE 'designer-anon'` 是**手动 SQL 用裸数字字面量**（`WHERE user_id=6`）触发，app 不走这条。→ 手动查 cost_ledger 用字符串比较（`user_id='6'`）或按行 id。

## 建议修复方向（开发，待 PM 排期）
1. 旧流统一改用 **`CurrentUserDep` 的 Bearer 身份作 user_id**、删 `UserIdDep`/`X-User-Id`（对齐 listing.py:39 范式）。
2. async_generation 路由级也补 `login_required`（与其余 login_required 路由一致，去掉「路由级未挂、靠 handler 自带」的不一致）。
3. 复核 projects/selection/export/revision/customers 是否也有可伪造归属。
4. 关联 ISSUE-0006-WP-G「全量挂鉴权」，可一并收口。
> 先确认这些旧流是否仍在 prod 暴露/使用（web UI 主用 listing）：若旧流 mounted-but-unused，则是潜伏漏洞（P2）；若活跃使用且真实计费，升 P1。

## 处理记录
- 2026-06-09 [开发] 运维清 cost_ledger 撞到 designer-anon（#274）→ coordinator 派查（#276）。读码确认 = 旧流用可伪造 X-User-Id 做 cost/job 归属（非 Bearer 身份），listing 已修对、旧流未迁移。开本条，owner→PM 排期（跨多旧流 refactor + 需确认旧流 prod 暴露面）。app 查询无 1292 风险（全字符串绑定）已排除。
