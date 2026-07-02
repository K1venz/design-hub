---
id: ISSUE-0051
title: 「帮我设计」对话历史持久化 + 回显（DeerFlow 式多会话完整存档）
status: 已确认        # 用户提需求 + 亲签两表 schema（2026-07-02）；设计定稿、实现棒可开
severity: P1          # 用户直接提需求；chat MVP 会话内存态刷新即丢的核心补齐
reporter: PM          # 用户提需求（本会话），PM 主持 brainstorm 定稿 + 开条
owner: 开发           # dev 第一棒（迁移建 2 表[已签]→持久化层→会话 API）；frontend-b 回显 UI 随后
created: 2026-07-02
updated: 2026-07-02
related:
  - PRD: §3.14.1 对话历史持久化 + 回显
  - issue: ISSUE-0048（「帮我设计」chat MVP，会话内存态不落库=本条前身）
  - 调研: 调研-DeerFlow式对话创作入口-2026-07.md P2「会话持久化=触发 DB 亲签铁律、先问用户」
  - code: image-code application/chat/（ChatOrchestrator + InMemorySessionStore→迁 DB 转录）、interface/api/routes chat
  - 参考形态: DeerFlow（侧栏历史会话列表 + 点入回显完整线程）
---

## 定性（用户提需求 2026-07-02）
把「帮我设计」chat 会话从**内存态（刷新即丢）**升级为**持久化多会话存档 + 回显**：对标 DeerFlow——侧栏列出用户全部过去会话，点任意一条回到完整对话线程，**并回显当时的出图结果图**。范围=用户拍板 **A 多会话完整存档、一步到位**。

## ✅ schema（用户亲签 2026-07-02，DB 铁律满足）
> 用户本会话明确「你签这两张表吗？」→「ok…你开工吧」= **亲签**。两表新增、**不动任何现有表**。dev 动迁移的前置已解锁。
- **`chat_session`**：`id`(uuid PK) / `user_id`(归属·索引·与 listing_job.user_id 同口径字符串) / `title`(首条用户消息截断自动生成) / `created_at` / `updated_at`(最近消息·列表倒序)。
- **`chat_message`**：`id`(uuid PK) / `session_id`(FK→chat_session · ON DELETE CASCADE · 索引) / `seq`(会话内顺序·回显排序) / `role`(user/assistant) / `content`(文本) / `job_id`(可空·关联 listing_job 回显图) / `attachment_upload_ids`(可空·用户带图轮 upload_id 回显缩略图) / `created_at`。
- 具体 SQL 列类型 dev 对齐现有模型定稿（同套图 4 列/复刻 2 列粒度，语义以上为准）；**确需偏离本签字 schema（加列/改语义）→ 再报用户亲签**（铁律）。

## 已定设计（用户 brainstorm 逐条确认）
1. **存转录、不存事件回放**：过程态（流式吐字/步骤条/费用卡）不落库；只存 user 消息 + assistant 最终答复 + 该轮 job_id。
2. **图片回显 = job_id 引用、绝不存签名 URL**：⚠️ 签名 TOS URL 有 TTL 会过期（实拍踩过 10s 坑）。图的永久身份=`image_key`，已在 listing_image 永久存；回显时 job_id→listing_image→image_key→**现签新 URL**→复用出图结果卡（与出图历史页同机制、零冗余）。**未选**「冗余 image_key 自包含」变体（jobs 正常不删，YAGNI）。
3. **owner 隔离 = 每用户会话独立**（用户口径）：人人平等、都能建/删**自己的**会话（非角色门槛）；越权访问他人会话 id → **404 anti-enum**（沿 ISSUE-0032/0039/0041）——这是「会话独立」的实现兜底、不是能力限制。
4. **硬删**（children-first CASCADE）；标题 MVP=首条用户消息截断。
5. **confirm_token 等过程态仍留内存**（10min TTL 一次性，不落库）；持久化的只有转录。

## API（复用现有鉴权/owner 隔离，dev 定 openapi）
- `POST /chat/messages`：首条建会话、之后追加（带 session_id）；每轮落转录。
- `GET /chat/sessions`：列我的会话（id/title/updated_at/消息数）。
- `GET /chat/sessions/{id}`：完整转录回显（越权 404）。
- `DELETE /chat/sessions/{id}`：删会话（越权 404、CASCADE 删消息）。
- 建议 `ChatSessionRepository` 端口 + SQL 适配器；InMemorySessionStore 转录职责迁 DB。

## 前端回显（DeerFlow 式，frontend-b）
「帮我设计」页加会话侧栏/列表 → 点一条拉转录回显（文字气泡 + job_id 重渲染出图结果卡 + 带图缩略图走 uploadPreviewUrl）；「新对话」开新会话；进入=最近会话或空态。

## 验收标准（QA）
1. **持久化不丢（P0）**：发消息后刷新/重进，会话与消息仍在。
2. **多会话列表 + 回显（P0）**：侧栏列全部会话；点历史会话回显完整线程 + **当时出图结果图正常回显**（现签 URL 不过期）。
3. **owner 隔离（P0）**：只见/删自己会话；越权他人会话 id→404 anti-enum。
4. **删除（P1）**：删会话级联删消息、列表消失、他人不受影响。
5. **零回归（P0）**：现有 /chat 实时对话/出图/费用闸 + 工作台全链零变化。
6. **fail-fast（P1）**：DB/持久化错不静默吞。

## 范围外（YAGNI，二期）
会话重命名 / 全文搜索 / 事件级完美回放 / 跨设备实时同步 / 导出对话 / 自动过期清理 / 冗余 image_key 自包含变体。

## 处理记录
- 2026-07-02 [PM] 用户提需求「存储对话历史 + 回显、参考 DeerFlow」→ PM 主持 brainstorm：范围拍 A（多会话完整存档一步到位）→
  逐条确认设计（存转录非回放 / 图片 job_id 引用不存签名 URL / owner 隔离=会话独立 / 硬删 / 标题自动）→ **用户亲签两表 schema**。
  PM 落 PRD §3.14.1 + 开本条（含签字 schema + 全设计 + 验收 6 条 + 分工）。owner=开发（迁移建表[已签]→持久化层→会话 API），
  frontend-b 回显 UI 随 openapi，QA 验收。**仍内测灰度**（7.B/7.A 前置不变）；**上线前迁移须带 mysqldump 备份**（DROP 类纪律沿 ISSUE-0046）。
  待 coordinator 编排开工。
- 2026-07-02 [PM] **DB 签字 gate 闭合确认**（dev #939 纯读准备亮牌）：dev 确认签字两表**零偏离可落**——
  id=uuid String(32)(同 listing_job)/user_id String(64)/title String(255)/attachment_upload_ids=JSON 列表/
  FK CASCADE + 索引(user_id·updated_at·session_id)，**无加列无改语义→无需再签**。且**现有 /chat/messages+/chat/confirm
  SSE 契约完全不变**（落库是服务端透明加，frontend live 流零改零回归），仅新增 3 会话 API（shape 对齐 0051 设计：
  列表 {id,title,updated_at,message_count} / 详情 {messages:[{seq,role,content,job_id?,attachment_upload_ids?}]} / DELETE，
  越权 404 CASCADE）。编排=dev 等 coordinator「image-code 已释放」口令即执行（避 /showcase 部署 rsync 捎带半成品）。
