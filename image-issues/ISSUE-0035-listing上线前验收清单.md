---
id: ISSUE-0035
title: listing 一键出图 · 上线前验收清单（QA 逐项跑，全绿放行）
status: 已确认        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起
severity: P1          # listing 上线闸门：QA 系统性验收，决定能否交付
reporter: PM
owner: QA             # 待 QA 进群接：逐项执行，结果回填本条
created: 2026-06-08
updated: 2026-06-08
related:
  - PRD: §3.12（listing 全章）/ §3.12.6 验收口径
  - issue: 0030(持久化+历史)/0031(输入图回显)/0034(海报签名url)/0016(图床)/0026(两步上传)/0011(SSE鉴权)
---

## 背景
listing 一键出图主线约 80%，后端 + 前端主体已落地（两步上传 + SSE + 历史持久化 + 图床 + 火山 TOS 已上 prod）。
上线前需 QA 系统性验收。**本条 = 上线 checklist**，QA 逐项跑、结果回填；A–E 全绿 + F 统计达标即可放行。
环境：受控环境（真 MySQL + 真 gpt-image，**真实出图一律 n=1 控成本**）；先 `alembic upgrade head`(迁移 6420ac5f02e7) 建表。

## A. 出图链路（端到端）
- [ ] **A1 两步上传**：`POST /uploads`(字段 `file`，≤10MB，png/jpg/webp)→`{id,url}`；超大/非白名单/空→4xx；`GET /uploads/{id}?access_token=`→图，无 token→401，缺失→404。（0026 已验，回归）
- [ ] **A2 出图入参**：`POST /listing/generate`(JSON `{upload_ids≤3,prompt,ratio,n,modifiers{}}`)→job_id；upload_ids 0/>3→400、不存在 id→4xx、空 prompt/未知下拉值→400。
- [ ] **A3 SSE**：`GET /listing/{job_id}/events?access_token=` → `task_started→model_called→image_generated×N(逐张)→task_completed`；无 token→401。
- [ ] **A4 N 张并发**：n=3/5/7 真出 N 张候选（并发，每张独立 seed/cost）；部分失败→任务 `部分完成`、成功图照出。

## B. 持久化 + 历史（0030）
- [ ] **B1 落库**：出图结束写 `listing_job`(完成/部分完成/失败) + `listing_image`(每张) + `listing_job_input`(输入图)；失败也落库(error + 0 成本)。
- [ ] **B2 历史列表**：`GET /listing/jobs?limit=&offset=&q=` → 本人、时间倒序、分页(limit 默认 20/1..100、offset≥0)、`q` 模糊搜本人；字段齐(first_image_url/image_count/...)。
- [ ] **B3 历史详情**：`GET /listing/jobs/{id}` → 本人 200(images[]/input_urls[]/元数据)。

## C. 回显复验（真数据，前端 frontend-b 配合走查）
- [ ] **C1 输入图回显(0031)**：prod/受控环境历史详情输入图正常显示、不 404。（dev：prod 已闭环、本地 dev 残留不修，QA 复验 prod）
- [ ] **C2 海报过期签名 url(0034)**：海报流改存 key + 现签后，海报回看 / 导出不再过期 404。（dev：830017e/210aba7 已改，QA 复验回看+导出）
- [ ] **C3 图床(0016)**：listing/项目/选稿各 Out 图 url 经 signer 现签、前端真图可显(非 file://)。残留：mock provider 吐 `mock://`(免费 mock 看不到占位图，低优先，**不阻断真实出图**)。

## D. 权限 / 安全（重点）
- [ ] **D1 越权隔离**：A 用户 token 取 B 的 job_id → **404**(不泄露存在性)；历史/出图一律按 JWT 身份，不认 X-User-Id。
- [ ] **D2 鉴权**：无 Bearer→401；SSE 无 `?access_token=`→401。

## E. 成本
- [ ] **E1 守门**：CostGuard 预扣→按实回正；provider 失败回滚预扣(额度不漏)；N 张并发各算成本。

## F. 验收口径（PRD §3.12.6，质量闸门，需花费采样）
- [ ] **F1 首次可用率**：跑一批花生/FOOD 样本，统计 **≥ 50–60%**(纯直出务实口径，不套两阶段 70%)。
- [ ] **F2 时延**：单次 N 张 **P95 ≤ 5 分钟**(N≤7，并发)。
- [ ] **F3 非法入参**：全 4xx fail-fast，未出图零成本。

## 放行标准
A–E 全绿 + F 统计达标（F1 样本若不足 50%，PM 据样本重定口径或开优化项，不阻断 A–E 闸门）。

## 依赖 / 前置
- QA 进群 + 受控环境（真 MySQL + 真 gpt-image，n=1 控成本）。
- C2/C3 等 dev 翻牌 0034→待验证、核 0016 残留（dev 群内承诺）。
- C1/C2/C3 真数据走查与 frontend-b 联动（其 schema.d.ts 对齐后）。

## 处理记录
- 2026-06-08 [PM] 据 coordinator 群内确认「listing 验收清单由 PM 出」，将 PRD §3.12.6 验收口径扩成本上线 checklist（A 链路/B 持久化历史/C 回显复验/D 权限/E 成本/F 质量口径）。
  纳入群里 dev 读码核对的真实状态：0031 prod 已闭环(本地 dev 残留不修)、0034 代码已改存 key+现签(待翻牌)、0016 核心已解决(残留 mock 占位低优先)。
  owner=QA，待 QA 进群接单逐项跑。**当前主线瓶颈 = QA 未进群**（需用户在 QA 窗口 join）。
