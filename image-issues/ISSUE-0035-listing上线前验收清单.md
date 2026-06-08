---
id: ISSUE-0035
title: listing 一键出图 · 上线前验收清单（QA 逐项跑，全绿放行）
status: 已关闭        # 待复现 | 已确认 | 修复中 | 待验证 | 已修复 | 已关闭 | 无法复现 | 挂起（A–F 全绿 + 用户拍定 base 档位 → 验收收官）
severity: P1          # listing 上线闸门：QA 系统性验收，决定能否交付
reporter: PM
owner: QA             # 已关闭。⚠️ 验收闭环≠能上线，上线前硬 gate 见 ISSUE-0037(prod 换 key+QA 复验) + PM 上线清单(文案质控/单价)
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
- [x] **A1 两步上传**：`POST /uploads`(字段 `file`，≤10MB，png/jpg/webp)→`{id,url}`；超大/非白名单/空→4xx；`GET /uploads/{id}?access_token=`→图，无 token→401，缺失→404。（0026 已验，回归）
- [x] **A2 出图入参**：`POST /listing/generate`(JSON `{upload_ids≤3,prompt,ratio,n,modifiers{}}`)→job_id；upload_ids 0/>3→400、不存在 id→4xx、空 prompt/未知下拉值→400。
- [x] **A3 SSE**：`GET /listing/{job_id}/events?access_token=` → `task_started→model_called→image_generated×N(逐张)→task_completed`；无 token→401。
- [x] **A4 N 张并发**：n=3/5/7 真出 N 张候选（并发，每张独立 seed/cost）；部分失败→任务 `部分完成`、成功图照出。

## B. 持久化 + 历史（0030）
- [x] **B1 落库**：出图结束写 `listing_job`(完成/部分完成/失败) + `listing_image`(每张) + `listing_job_input`(输入图)；失败也落库(error + 0 成本)。
- [x] **B2 历史列表**：`GET /listing/jobs?limit=&offset=&q=` → 本人、时间倒序、分页(limit 默认 20/1..100、offset≥0)、`q` 模糊搜本人；字段齐(first_image_url/image_count/...)。
- [x] **B3 历史详情**：`GET /listing/jobs/{id}` → 本人 200(images[]/input_urls[]/元数据)。

## C. 回显复验（真数据，前端 frontend-b 配合走查）
> dev 已翻牌(commit bb4eb9d)：C1/C2/C3 均 **owner→QA、待验证**；隧道连 prod 真数据复验。
- [x] **C1 输入图回显(0031)**：prod 历史详情输入图正常显示、不 404。dev：prod 已闭环、本地 dev 残留判定不修(830017e)——QA 隧道连 prod 复验；**本地 dev 的 404 是已知不修残留、不算 bug**。
- [x] **C2 海报签名 url(0034, owner→QA)**：海报流改存 key + 读时 MediaUrlSigner 现签、导出从 TOS generate 桶按 key 现读(8b5360f/210aba7/830017e)。**验法(dev #48 推荐第一种，本地 /img 即可、零 TOS 依赖)**：海报流出一张 → 查 DB `generated_image.url` 存的是**文件名 key(非带 `?X-Tos` 的签名 url)** + 回看/导出能读 → 证明「存 key 不存 url」生效，**不用配 TOS、不用等 TTL**；勿拿 prod 旧死链误判。无需迁移；同根「回看404」条 owner=QA 合并验。
- [x] **C3 图床(0016, owner→QA, P1→P3)**：方案①「图能 HTTP 加载」已达成(LocalImageStore 不再 file://、各 Out 经 signer 现签、真实出图可直显)。仅余方案②(mock provider 可视占位)押后低优先，只影响零成本 mock 联调、**真数据不受影响**。

## D. 权限 / 安全（重点）
> **只验 listing 范围的 designer 间越权 + 鉴权，不验 manager 专属端点**(/dashboard、/admin 属角色矩阵 ISSUE-0006-WP-G，不在 listing 上线)。纯 designer 跑(dev #37 自注册 2 个)，**不 seed manager**。
- [x] **D1 越权隔离**：A 用户 token 取 B 的 job_id → **404**(不泄露存在性)；历史/出图一律按 JWT 身份，不认 X-User-Id。
- [x] **D2 鉴权**：无 Bearer→401；SSE 无 `?access_token=`→401。

## E. 成本
- [x] **E1 守门**：CostGuard 预扣→按实回正；provider 失败回滚预扣(额度不漏)；N 张并发各算成本。

## F. 验收口径（PRD §3.12.6，质量闸门，需花费采样）
- [x] **F1 首次可用率**：跑一批花生/FOOD 样本，统计 **≥ 50–60%**(纯直出务实口径，不套两阶段 70%)。
- [x] **F2 时延**：单次 N 张 **P95 ≤ 5 分钟**(N≤7，并发)。
- [x] **F3 非法入参**：全 4xx fail-fast，未出图零成本。

## 放行标准
A–E 全绿 + F 统计达标（F1 样本若不足 50%，PM 据样本重定口径或开优化项，不阻断 A–E 闸门）。

## 依赖 / 前置
- QA 进群 + 受控环境（真 MySQL + 真 gpt-image，n=1 控成本）。
- C2/C3 等 dev 翻牌 0034→待验证、核 0016 残留（dev 群内承诺）。
- C1/C2/C3 真数据走查与 frontend-b 联动（其 schema.d.ts 对齐后）。

## QA 验收进度（2026-06-08 · server qa 实例 QA_BASE=localhost:8444 · 镜像 main HEAD 612d474→797ca06 · **A–F 全绿**）

> 环境：独立 `design_hub_qa` 库 + 独立 qa TOS 桶（`bucket-design-hub-qa-generate/-upload`）+ TTL=10，prod 零触碰（安全闸已 fingerprint 复核）。脚本：`image-qa/listing_real_boundary.py`、`listing_history_e2e.py`、`listing_acceptance_batch.py`。

| 项 | 结果 | 证据 / 说明 |
|---|---|---|
| A1 两步上传 | ✅ | boundary：合法→200{id,url}、>10MB/gif/空→400、预览 200/401/404 |
| A2 入参 fail-fast | ✅ | boundary：upload_ids 0/>3、n=0/8、ratio 非法/4:3、空 prompt、未知下拉 → 全 400；无 Bearer/SSE 无 token→401 |
| A2+ 上传归属隔离(新增) | ✅ | 引用他人 upload_id→400（ISSUE-0032 `owns()`） |
| A3 SSE happy | ✅ | 见真章+batch：`task_started→model_called→image_generated→task_completed`，真图 TOS qa-generate 桶 200 |
| A4 N 张并发 | ✅ | n=3/5/7 各一次：候选 3/5/7 全齐、**distinct seeds**、全成功（193/157/191s）。注：本批无自然部分失败→全"完成"，"部分完成"路径属结构/单元覆盖（需稳定 4xx 诱发） |
| B1 落库 | ✅ | 成功(完成/img/cost)+失败(失败/cost=0/img=0) 都落库；listing_image image_key=裸 key |
| B2 历史列表 | ✅ | 本人/倒序/分页(limit 1..100、offset≥0)/字段齐 |
| B3 历史详情 | ✅ | 本人 200，元数据+input_urls+多图(n=7)齐；frontend 满态走查无破 |
| C1 输入图回显(0031) | ✅ | server TOS 上 200：input_url=qa-upload 桶现签 GET 200 image；frontend 肉眼复看亦好。**0031 闭环** |
| C2 海报签名 url(0034) | ✅ | generation 出 1 张双证：①DB `generated_image.url`=`8e61a4b3…png` **裸 key**(非签名 url) ②TTL=10 出图后等 11s 复读 GET 200(读时现签不过期)。**0034 闭环** |
| C3 图床(0016) | ✅ | 输入/输出图 url 经 signer 现签 GET 200 image(非 file://)；image_key 存裸 key。残留 mock `mock://` P3 不阻断 |
| D1 越权隔离 | ✅ | A 取 B 的 job→404；B 列表不含 A 的 job |
| D2 鉴权 | ✅ | 无 Bearer→401；SSE 无 access_token→401 |
| E1 成本守门 | ✅ | 失败回滚→cost=0；成功预扣→回正；job total_cost==Σ(每张 cost) 一致；N 张各算成本 |
| F1 首次可用率 | ✅ | 完成率 **11/11=100%**；QA 视觉初判可用率 **7-8/8=87.5-100%**（PM 逐字核：7/8 文案全对、样张8 `PRENIUM` typo=AI 通病非 base 特有）。**远超 50-60%** |
| F2 时延 P95 | ✅ | **P95=193s ≤ 300s PASS**；n=7 = **7 个并发单图调用**(dev #166 纠 #124：非 1 批量)，wall≈最慢单图 190.7s(非 7×串行)。base 速度可接受 |
| F3 非法入参 | ✅ | = A2，全 4xx fail-fast、零成本（boundary 22/22） |

**边界码（dev #93/797ca06，已复测 22/22）**：upload-id 错误态统一 **404「不存在或无权访问」**防枚举（B4 不存在 / B5 非法格式 / C1 他人 / A9 GET badid）；格式校验保留在**本人命名空间内**（owns()=True→load() 仍 400/404）。

**ISSUE-0037（gpt key）已解**：401(死 key)→ops 换有效 key →403(账号无 vip 权限)→改 base `gpt-image-2` 打通。验收全程真实出图 **0 浪费**（失败不计费、双阶段成本闸）；base 实际花费远低于系统占位价。

**✅ 验收结论：A–F 全绿、放行标准达标**（可用率 87.5-100% 远超 50-60%、F2 P95 193s PASS、E/D/C 全闭环）。仅样张8 `PRENIUM` typo = AI 直出通病、转「上线前文案质控」待办、**不阻断**。上线档位 **PM 建议锁 base**（成本省½ + 便利现成 key + 速度 PASS + 画质 user green），待用户拍。

## 处理记录
- 2026-06-08 [PM] 据 coordinator 群内确认「listing 验收清单由 PM 出」，将 PRD §3.12.6 验收口径扩成本上线 checklist（A 链路/B 持久化历史/C 回显复验/D 权限/E 成本/F 质量口径）。
  纳入群里 dev 读码核对的真实状态：0031 prod 已闭环(本地 dev 残留不修)、0034 代码已改存 key+现签(待翻牌)、0016 核心已解决(残留 mock 占位低优先)。
  owner=QA，待 QA 进群接单逐项跑。**当前主线瓶颈 = QA 未进群**（需用户在 QA 窗口 join）。
- 2026-06-08 [QA] 进群接单，server qa 实例第一轮跑：非出图链路全绿（boundary 20/22、B 失败落库、B2/B3、**C1 输入图回显 200**、D1/D2、E 失败回滚），出图链路（A3/A4/C2/F + B/E 成功态）被 **ISSUE-0037（gpt key 401 失效）阻塞、零成本撞出**（双阶段成本闸：失败不计费 total_cost=0）。边界 A9 确认预期、B4 已修(797ca06)待复测。owner=QA，等 0037 key 修复（ops）+ 容器从 HEAD 797ca06 重 build 后续跑。
- 2026-06-08 [QA] **验收闭环**：ISSUE-0037 解决后（ops 换有效 key + 改 base `gpt-image-2` + 容器 797ca06 重建）续跑全绿——A3 见真章 17/17、A4 n=3/5/7 候选齐 distinct seeds、B 成功/失败落库、C1 输入图回显 200、**C2/0034 双证(DB 裸 key `8e61a4b3…png` + TTL=10 复读 200)**、C3 图床现签、D1 404、D2 401、E1 成本一致、**F1 完成率 100%/可用率 87.5-100%、F2 P95 193s PASS**、boundary 22/22(upload-id 错误态统一 404 防枚举)。8 花生样张落盘 `image-qa/共评样张/` + index.md(QA 5 维初判)供共评；PM 逐字核 7/8 文案全对(样张8 `PRENIUM` typo 转上线前质控待办)。**A–F 全绿、放行标准达标**。上线档位 PM 建议 base、待用户拍。验收全程真实出图 0 浪费(失败不计费)、守 60 张硬顶(实用 24 张)。owner=QA，待用户定档后翻「已修复→已关闭」。
- 2026-06-08 [QA] 用户拍板 **base 锁定为 listing 上线档位**（coordinator #163）→ listing 验收全线收官，本条翻**「已关闭」**。⚠️ 提醒：**验收闭环 ≠ 能上线**——上线前硬 gate 见 ISSUE-0037（prod 换有效 key + QA 复验 prod 真出图，否则用户上线即 401）+ PM 上线清单（文案质控治 PRENIUM 类 typo / 系统占位单价 ¥1.19→base 真实 $0.05 更新）。详见 memory [[project_listing_launch_gates]]。
