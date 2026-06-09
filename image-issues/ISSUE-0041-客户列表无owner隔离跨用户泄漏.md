---
id: ISSUE-0041
title: 客户列表无 owner 隔离 —— 新用户看到他人/遗留客户（"拍拍熊"），疑似跨用户数据泄漏
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 若客户应私有=跨用户数据泄漏(同 0039 类);若设计为组织共享则降级为"清遗留测试数据"
reporter: 用户(prod 实测) / coordinator 转
owner: PM             # 球在 PM/用户:先定产品性质(客户私有 vs 组织共享);若私有→批 schema 迁移后交 dev
created: 2026-06-09
updated: 2026-06-09
related:
  - code: image-code/src/design_hub/infrastructure/db/customer_repo.py:59-61（list = select(Customer) 全表无 user_id 过滤）
  - code: image-code/src/design_hub/infrastructure/db/models.py:27-38（Customer 表无 user_id/owner 列）
  - code: image-code/src/design_hub/interface/api/routes/customers.py:23（list_customers 不带身份）
  - code: image-code/src/design_hub/interface/api/routes/listing.py:76（对照:listing_job 按 user_id 隔离的正确范式）
  - issue: ISSUE-0039（旧流可伪造归属，同类隔离问题）/ ISSUE-0032（anti-enumeration 范式）
---

## 现象
prod 真实用户**新注册账号**在「客户」页看到一个固定的「拍拍熊」花生食品客户（用户实测，coordinator #413）。

## 根因（读码）
- `customer` 表**没有 owner/user_id 列**（models.py:27-38 字段仅 name/contact/industry/brand_color/styles/taboos/sizes/created_at）。
- `GET /customers` → `customer_repo.list()` = `select(Customer).order_by(Customer.id)`（customer_repo.py:59-61）**全表无过滤** → **所有用户看到所有客户**。
- `POST /customers` 创建时**不记录 owner**（无身份字段可记）。
- 「拍拍熊」= 早前某人（用户/测试）经 POST /customers 建的客户记录（**系统无客户 seed**），因列表全局可见而对每个新用户显示。
- 对照 listing：`listing_job` 有 `user_id` 列、`/listing/jobs` 按本人过滤（listing.py:76）——客户没跟这个隔离范式。

## 待拍（决定是 bug 还是设计）
**① 产品定性（PM/用户）**：客户档案是「每个设计师私有」还是「组织级共享」？
- **私有** → 现状 = 跨用户数据泄漏漏洞（同 ISSUE-0039 类）、**P1**；
- **组织共享** → 现状 = 设计预期，「拍拍熊」只是遗留测试数据，清掉即可、降级。

## 建议修复（若定"私有"，涉 DB schema 变更）
> ⚠️ 涉建表/迁移，按本仓铁律 **dev 不擅动、需用户先批 schema**。
1. `customer` 表加 `user_id` 列（additive 迁移；运维部署时跑）。
2. `POST /customers` 记当前 Bearer 身份为 owner（route 加 CurrentUserDep + service/repo 透传 user_id）。
3. `GET /customers` 按本人 user_id 过滤；`GET /customers/{id}` 越权→404（anti-enum，沿用 ISSUE-0032，不泄露存在性）。
4. 历史无 owner 的旧客户（"拍拍熊"等）迁移归属处理：归某管理账号 / 直接清 / 标记——需定。

## 处理记录
- 2026-06-09 [开发] coordinator #413 转用户 prod 实测（新账号见"拍拍熊"客户）→ 读码确认：customer 表无 owner 列、list 全表无过滤 = 全局可见。开本条。owner→PM：先定产品性质（私有/共享）；若私有→修复涉 customer 表加 user_id 迁移、按铁律需用户批 schema 后 dev 实现（route+service+repo+迁移，对齐 listing_job/0032 范式）。bug B（新建任务按钮无反应）归 frontend-b（后端无建任务端点、疑前端残骸）。
