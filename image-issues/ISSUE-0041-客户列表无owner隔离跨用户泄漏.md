---
id: ISSUE-0041
title: 客户列表无 owner 隔离 —— 新用户看到他人/遗留客户（"拍拍熊"），疑似跨用户数据泄漏
status: 已修复        # QA 验收 5/5 全 PASS（qa 回归 1-4 + prod smoke 5）→ 待 PM 终验收关 | 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # 用户拍定客户私有 → 跨用户数据泄漏漏洞(同 0039 类)，P1 严重(prod 真泄漏、非阻断)
reporter: 用户(prod 实测) / coordinator 转
owner: 产品(PM)      # QA 验收 5/5 全 PASS（qa 回归1-4 + prod smoke 5）、prod 漏洞消除 → 球交 PM 终验收关 0041
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

## 决议（用户已拍 2026-06-09 / coordinator #423）
**产品定性 = 客户档案「按用户私有」**（PM/coordinator/dev/frontend 一致推荐，用户批准）→ 现状 = 跨用户数据泄漏漏洞（同 ISSUE-0039 类）、**P1 严重**。
- **用户批准 schema 迁移**：customer 表加 `user_id` 列。
- **「拍拍熊」等无主旧客户 → 删**（迁移先 `DELETE FROM customer` 清无主测试数据，再加 NOT NULL 列）。

## 建议修复（若定"私有"，涉 DB schema 变更）
> ⚠️ 涉建表/迁移，按本仓铁律 **dev 不擅动、需用户先批 schema**。
1. `customer` 表加 `user_id` 列（additive 迁移；运维部署时跑）。
2. `POST /customers` 记当前 Bearer 身份为 owner（route 加 CurrentUserDep + service/repo 透传 user_id）。
3. `GET /customers` 按本人 user_id 过滤；`GET /customers/{id}` 越权→404（anti-enum，沿用 ISSUE-0032，不泄露存在性）。
4. 历史无 owner 的旧客户（"拍拍熊"等）迁移归属处理：归某管理账号 / 直接清 / 标记——需定。

## 验收标准（PM 落，coordinator #423；QA 回归 + ops prod smoke）
对齐 ISSUE-0032（anti-enum）/ ISSUE-0039（隔离范式），镜像 listing_job owner 隔离：
1. **列表隔离**：A 建客户后，B `GET /customers` **看不到 A 的客户**；列表只返本人。
2. **越权 404**：`GET /customers/{他人id}` → **404**（anti-enum，与不存在/畸形 id 不可区分，不泄漏存在性）。
3. **create 记 owner**：`POST /customers` 落库带当前 Bearer user_id；本人随后可见、他人不可见。
4. **迁移生效**：迁移后 `customer` 表有 `user_id` NOT NULL 列 + 索引；**"拍拍熊"等无主旧数据已清**（新账号 `GET /customers` 为空）。
5. **prod smoke**：部署后新注册账号 `GET /customers` 返回空、看不到任何他人客户。
> 三方分工：dev 实现（镜像 listing_job 范式 7 处）→ QA qa 回归（1–4）PASS → ops 部署 prod（跑 alembic 迁移、⚠️碰 prod DB 删无主+加列，**先备份 customer 表 + 可回滚**）→ QA prod smoke（5）。

## 处理记录
- 2026-06-09 [开发] coordinator #413 转用户 prod 实测（新账号见"拍拍熊"客户）→ 读码确认：customer 表无 owner 列、list 全表无过滤 = 全局可见。开本条。owner→PM：先定产品性质（私有/共享）；若私有→修复涉 customer 表加 user_id 迁移、按铁律需用户批 schema 后 dev 实现（route+service+repo+迁移，对齐 listing_job/0032 范式）。bug B（新建任务按钮无反应）归 frontend-b（后端无建任务端点、疑前端残骸）。
- 2026-06-09 [PM] coordinator #423 转**用户批准修复计划**：产品定性=客户私有（全队一致推荐）+ 批准 schema 迁移（customer 加 user_id）+「拍拍熊」等无主数据删。PM 落验收标准（列表隔离/越权 404/记 owner/迁移生效/prod smoke）、定级 **P1 严重**（prod 真泄漏、非阻断）。**status→修复中、owner→开发**（实现 7 处镜像 listing_job 范式 → QA 回归 → ops 部署备份+回滚 → QA prod smoke）。二次编辑（§3.12.13 定稿）这轮 bug 修完 + 用户签 schema 后再启动。
- 2026-06-09 [QA] **qa 复现实锤 + 隔离回归就位**（脚本 `image-qa/customer_isolation_regression.py`，commit e5f0914）。qa env 跑出铁证：B（新号）越权 `GET /customers/{A的id}` → **HTTP 200 + 泄漏 name='A的拍拍熊'**；B 列表 ids=[1,2,3] == A 列表（两个用户看到完全相同的全表）。7 断言中 4 个隔离用例 FAIL（=修前预期）、3 个 sanity PASS。脚本断言全按修复后预期写（镜像 listing_job 隔离 + 0032 anti-enum 404），**dev 交付后同一脚本翻全 PASS = 验收标准 1–4 通过**；prod smoke（标准 5）另写只读探针、部署后跑（不在 prod 乱建客户）。owner 仍=开发（待 dev 实现）。
- 2026-06-09 [QA] **qa 回归翻全 PASS、放行部署**（dev 9c80064 + 迁移、ops #435 已重 build qa 到 9c80064 + 迁移 apply）。同一脚本 red→green 实证（修前后两跑同环境）：修后 B 越权 GET A 客户=**404**、A 列表=[4]/B 列表=[5] 各自隔离、旧 [1,2,3] 已清 → 全 7 PASS。**验收 1-4 qa 通过**：①列表隔离 ②越权404 ③create记owner ④迁移生效（ops 确认 user_id varchar(64) NOT NULL + 拍拍熊清；回归功能侧佐证 create 不 500=列在、旧数据清=DELETE 跑过）。剩 ⑤ prod smoke 等 ops 部署 prod 后跑（脚本 `customer_isolation_prod_smoke.py`，commit 2ffb934）。**status 仍修复中、owner→运维**（球在 ops 部署 prod）；部署后 QA prod smoke PASS → PM 终验收关。
- 2026-06-09 [QA] **prod smoke PASS、验收 5/5 全绿、prod 漏洞消除**（ops #437 部署 9c80064 + 迁移 apply prod：customer 行数=0 拍拍熊已删、user_id NOT NULL 列加、zhaokai 数据完整、扩展备份 `/root/bugC-backup-20260609.sql` + 镜像 `rollback-e8cbe79` 在手）。QA prod 只读探针：新账号注册 → `GET /customers` → **HTTP 200 返回 `[]`（空）** = 验收标准 5 绿（新账号不再看到拍拍熊/他人客户）。**五条验收全达成**：①列表隔离 ②越权404 ③create记owner ④迁移生效 ⑤prod新账号列表空。客户跨用户泄漏（同 ISSUE-0039 类）在生产消除。探针只读、未在 prod 建客户；留 1 个 qa-test 注册号 `qa-custiso-prod-1781002826@example.com`（ops 可后清）。**status→已修复、owner→PM 终验收关 0041。**
