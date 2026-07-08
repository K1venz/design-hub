---
id: ISSUE-0059
title: chat 改造 A 线——边界三环（大胆）+ 知识库（随功能同步）+ harness 重构（四段 prompt·上下文裁剪）
status: 修复中        # spec 定稿派单；PM 知识库首版内容已起草(draft)、dev harness 重构可先行
severity: P2          # 用户直接提需求（chat 聊得大胆+知识库+harness 优化）；体验/获客；非资损非阻断
reporter: PM          # 用户 2026-07-08 提需求（coordinator #1031 转达），spec 定稿 97c4978，PM 开条
owner: PM+开发        # PM 起草知识库内容(✅ draft)+DoD 流程；dev 落 harness(知识注入+四段prompt+上下文裁剪)+落知识库文件
created: 2026-07-08
updated: 2026-07-08
related:
  - PRD: §3.14「帮我设计」chat（本条重定义其边界=三环）、§3.14.2 chat 知识化+三环
  - spec: docs/superpowers/specs/2026-07-08-chat-knowledge-categories-design.md（coordinator 定稿 97c4978，A 线）
  - issue: ISSUE-0060（B 线品类扩展，并行独立）、ISSUE-0048/0051（chat 主线+历史持久化，本条 harness 不动其契约）
  - 交接: image-prd/chat-knowledge-base-v1-draft.md（PM 起草的知识库首版内容 → dev 落 image-code config/chat_knowledge.md）
  - 铁律: 方案 C 零框架零依赖不变；核心出图环卡链/费用闸/频控铁律不动；安全地板不松（7.B 公众全量硬前置不变、现内测+登录墙）
  - 群聊: image-gen#1 #1031（coordinator 派单）
---

## 定性（用户 2026-07-08 提需求，coordinator #1031 转达）
用户要「chat 聊得**大胆**一些、知识库=平台所有功能且随功能更新同步、harness 优化」。→ 重定义 chat 边界为**三环** + 建**知识库单一事实源**（随功能同步）+ harness 重构（四段 prompt + 上下文裁剪），**方案 C 零框架零依赖不变**。

## A1. 边界三环（「大胆」的精确含义）
1. **核心环（不变）**：出图参数收集→费用确认→出图，**卡链/费用闸/频控铁律全不动**。
2. **知识环（新增）**：答**平台任何功能**的怎么用/多少钱/在哪点——**依据知识库、没有的明说「暂不支持」不编造**。
3. **顾问环（新增=「大胆」）**：电商出图/营销视觉通用建议（选图型/比例、卖点文案怎么写更抓人、平台风格差异等）+ 可自然聊用户产品与生意。
- **安全地板（不松）**：违法违规/涉政涉黄/与平台完全无关的敏感话题仍拒（7.B 内容安全公众全量硬前置不变、现内测+登录墙）。

## A2. 知识库机制（随功能同步·关键）
- **单一事实源**：`image-code/src/design_hub/config/chat_knowledge.md`——平台功能地图（每功能：干什么/入口/价格/限制），**≤1500 token 预算**（每条消息注入、控成本）。
- **注入**：orchestrator 组 system prompt 时读入（启动加载、进程内缓存）。
- **✅ 首版内容 = PM 已起草** `image-prd/chat-knowledge-base-v1-draft.md`（套图/单图/复刻/编辑/帮我设计/历史/配方复用/价格¥0.4·免费5张/平台·比例·品类/记住我/明确不支持清单）→ **交 dev 落文件**（PM 不写 image-code）。
- **⚠️ 同步流程入 DoD（PM 承诺·长期）**：**功能上线记录必勾「chat 知识库同步」** + **QA 验收模板加「chat 能正确回答新功能」**。内容变更 PM 改 draft → dev 同步落文件。

## A3. harness 重构（方案 C 零框架不变，dev）
- **system prompt 四段结构**：persona（顾问人设）→ 知识库 → 工具契约 → 守则（安全地板+不编造+费用确认铁律）。
- **工具 description 打磨**（减少占位问句进参数的残余风险）。
- **长会话上下文裁剪**：转录 >20 轮只带**最近 20 轮 + 首轮**（**DB 转录仍全量存**=0051 不动，只裁 LLM 上下文）。
- 不引框架、不加新依赖。

## 验收标准（QA，A①-⑤，零成本 mock/真豆包澄清轮）
① **知识环**：问「复刻怎么用/出图多少钱/历史在哪」答案与知识库一致；问知识库外（「能出视频吗」）明说不支持不编造。② **顾问环**：问「卖点文案怎么写好」给建设性建议、不再拒。③ **核心环零回归**：三条真路径 + 费用闸 + 0051 持久化不变。④ **安全地板**：违规话题仍拒。⑤ **长会话**：30+ 轮上下文裁剪生效且回答连贯。

## 范围外（YAGNI）
知识库自动从 PRD 生成（先人工同步）；A 线对公众开放边界（仍内测）。

## 处理记录
- 2026-07-08 [PM] 用户提需求（coordinator #1031 转达，spec 97c4978 A 线）→ PM 开条 + **起草知识库首版内容**
  （`image-prd/chat-knowledge-base-v1-draft.md`，≤1500 token 全功能地图）。落 PRD §3.14.2。
  **DoD 流程承诺入档**：以后功能上线记录勾「chat 知识库同步」、QA 模板加「chat 能答新功能」——PM 长期执行。
  分工：PM 内容(✅ draft)+DoD；dev 落 harness（知识注入 config/chat_knowledge.md + system prompt 四段重构 + 工具 description 打磨 + 上下文裁剪 >20 轮带最近20+首轮，DB 转录全量不动）+ 从 draft 落知识库文件。零框架零依赖。
  status=修复中、owner=PM(内容起草完)+开发(harness)。dev 可先做 harness 重构、知识库文件从 draft 落。真实用户 bug 随时打断。
