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
### 环境与成本口径（QA #35 抓矛盾 → coordinator/dev 细化 → PM 拍板）
**两套环境（读写分离，QA 绝不在 prod 刷出图）：**
- **读类 → 隧道连 prod 真数据**（只读、零成本、零污染）：B 列表/详情/分页/q、C 回显复验(0031/0034/0016)、D 越权404/401(取已存在 job_id)。不需迁移(prod 已在 head)。
- **写类 → 独立受控环境**（env 覆盖 DB_URL 指**非-prod** 真实 MySQL + **真 gpt**(presence-based，无 mock 开关，dev #44 env 清单)，绝不写 prod，空库先 `alembic upgrade head`）：A 出图链路、E 预扣回正/回滚、B 落库。ops 出受控库 + 后端起法。

**成本（用户/Leader 拍板放行：封顶 60 张 ≈ ¥71.4，#47 上调自 #43 的 25 张）：**
- 默认 **n=1**；边界/非法入参零成本(不出图)。
- **A4 并发 + F2 P95 各放行一次 n=3/5/7（共 15 张真实）**；F2 时延复用这批。
- **F1 首次可用率多采样**：60 张余量内多跑几组 happy(n=1) 凑样本、统计更准，别只靠 15 张估。
- 失败重试 / 边界复跑算在 60 张内自由支配；**接近 ~50 张先回 PM/coordinator**，别闷头超。
- ⚠️ provider **presence-based**(dev #44)：配 GPT_IMAGE_* 就真实出图、**无 mock 开关**——受控环境也真实计费，全程守 60 张硬顶。

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
> dev 已翻牌(commit bb4eb9d)：C1/C2/C3 均 **owner→QA、待验证**；隧道连 prod 真数据复验。
- [ ] **C1 输入图回显(0031)**：prod 历史详情输入图正常显示、不 404。dev：prod 已闭环、本地 dev 残留判定不修(830017e)——QA 隧道连 prod 复验；**本地 dev 的 404 是已知不修残留、不算 bug**。
- [ ] **C2 海报签名 url(0034, owner→QA)**：海报流改存 key + 读时 MediaUrlSigner 现签、导出从 TOS generate 桶按 key 现读(8b5360f/210aba7/830017e)。**验法(dev #48 推荐第一种，本地 /img 即可、零 TOS 依赖)**：海报流出一张 → 查 DB `generated_image.url` 存的是**文件名 key(非带 `?X-Tos` 的签名 url)** + 回看/导出能读 → 证明「存 key 不存 url」生效，**不用配 TOS、不用等 TTL**；勿拿 prod 旧死链误判。无需迁移；同根「回看404」条 owner=QA 合并验。
- [ ] **C3 图床(0016, owner→QA, P1→P3)**：方案①「图能 HTTP 加载」已达成(LocalImageStore 不再 file://、各 Out 经 signer 现签、真实出图可直显)。仅余方案②(mock provider 可视占位)押后低优先，只影响零成本 mock 联调、**真数据不受影响**。

## D. 权限 / 安全（重点）
> **只验 listing 范围的 designer 间越权 + 鉴权，不验 manager 专属端点**(/dashboard、/admin 属角色矩阵 ISSUE-0006-WP-G，不在 listing 上线)。纯 designer 跑(dev #37 自注册 2 个)，**不 seed manager**。
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

## QA 第一轮验收进度（2026-06-08 · server qa 实例 QA_BASE=localhost:8444 · 镜像 main HEAD 612d474）

> 环境：独立 `design_hub_qa` 库 + 独立 qa TOS 桶（`bucket-design-hub-qa-generate/-upload`）+ TTL=10，prod 零触碰（安全闸已 fingerprint 复核）。脚本：`image-qa/listing_real_boundary.py`、`listing_history_e2e.py`、`listing_acceptance_batch.py`。

| 项 | 结果 | 证据 / 说明 |
|---|---|---|
| A1 两步上传 | ✅ | boundary：合法→200{id,url}、>10MB/gif/空→400、预览 200/401/404 |
| A2 入参 fail-fast | ✅ | boundary：upload_ids 0/>3、n=0/8、ratio 非法/4:3、空 prompt、未知下拉 → 全 400；无 Bearer/SSE 无 token→401 |
| A2+ 上传归属隔离(新增) | ✅ | 引用他人 upload_id→400（ISSUE-0032 `owns()`） |
| A3 SSE happy | ⛔ 阻塞 | **ISSUE-0037**：gpt key 401 Invalid token，出图即时失败 |
| A4 N 张并发 | ⛔ 阻塞 | 同 0037 |
| B1 落库 | 🟡 半绿 | **失败也落库✅**（status=失败/cost=0/img=0）；成功落库等 0037 |
| B2 历史列表 | ✅ | 本人/倒序/分页(limit 1..100、offset≥0)/字段齐 |
| B3 历史详情 | ✅ | 本人 200，元数据+input_urls 齐 |
| C1 输入图回显(0031) | ✅ | **server TOS 上 200**：input_url=qa-upload 桶签名 url GET 200 image。0031 在 server 闭环（本地 dev 残留不影响 server） |
| C2 海报签名 url(0034) | ⛔ 阻塞 | 需 generation 出 1 张（等 0037）；验法=DB `generated_image.url` 裸 key + TTL=10 真复现 |
| C3 图床(0016) | 🟡 半绿 | 输入图签名 url 200✅；输出图 url 等 0037 |
| D1 越权隔离 | ✅ | A 取 B 的 job→404；B 列表不含 A 的 job |
| D2 鉴权 | ✅ | 无 Bearer→401；SSE 无 access_token→401 |
| E1 成本守门 | 🟡 半绿 | 失败回滚→cost=0✅；成功预扣→回正等 0037 |
| F1 首次可用率 | ⛔ 阻塞 | 等 0037（真实样本）；可用率需视觉评分（与 PM 共评） |
| F2 时延 P95 | ⛔ 阻塞 | 等 0037 |
| F3 非法入参 | ✅ | = A2，全 4xx fail-fast、零成本 |

**边界码 nuance（dev #93 已处置）**：A9 `GET /uploads/badid`→404 = 防枚举预期、保留不改；B4 `generate` 不存在 upload_id→已由 400 升级为统一 **404**（commit 797ca06）「不存在或无权访问」，**待 ops 重 build 后零成本复测**。

**当前唯一阻塞 = ISSUE-0037（gpt key 失效）**；非出图链路全健康。key 修复后续跑 A3/A4/C2/F + B/E 成功态 + B4 复测即可闭环。

## 处理记录
- 2026-06-08 [PM] 据 coordinator 群内确认「listing 验收清单由 PM 出」，将 PRD §3.12.6 验收口径扩成本上线 checklist（A 链路/B 持久化历史/C 回显复验/D 权限/E 成本/F 质量口径）。
  纳入群里 dev 读码核对的真实状态：0031 prod 已闭环(本地 dev 残留不修)、0034 代码已改存 key+现签(待翻牌)、0016 核心已解决(残留 mock 占位低优先)。
  owner=QA，待 QA 进群接单逐项跑。**当前主线瓶颈 = QA 未进群**（需用户在 QA 窗口 join）。
- 2026-06-08 [QA] 进群接单，server qa 实例第一轮跑：非出图链路全绿（boundary 20/22、B 失败落库、B2/B3、**C1 输入图回显 200**、D1/D2、E 失败回滚），出图链路（A3/A4/C2/F + B/E 成功态）被 **ISSUE-0037（gpt key 401 失效）阻塞、零成本撞出**（双阶段成本闸：失败不计费 total_cost=0）。边界 A9 确认预期、B4 已修(797ca06)待复测。owner=QA，等 0037 key 修复（ops）+ 容器从 HEAD 797ca06 重 build 后续跑。
