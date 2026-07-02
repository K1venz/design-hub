---
id: ISSUE-0049
title: 「帮我设计」chat agent 后端 pytest 测试债（方案 C 上线时以 e2e/冒烟验、单测未补齐）
status: 已确认        # backlog（coordinator #918 收口备忘，dev 下轮补）；非阻断
severity: P2          # chat 已上线 prod、e2e+验收 8/8 已过，但缺单测护栏=回归风险面
reporter: PM          # coordinator #918 收口备忘，PM 入档
owner: 开发           # dev 下轮补 chat 后端单测
created: 2026-07-02
updated: 2026-07-02
related:
  - issue: ISSUE-0048（方案 C「帮我设计」主线，已上线 prod）
  - code: image-code application/chat/（ChatOrchestrator + InMemorySessionStore）、infrastructure/providers/openai_compat_text（文本 LLM 适配器）、interface/api/routes chat（/chat/messages + /chat/confirm）
  - 群聊: image-gen#1 #918（收口备忘：chat pytest 测试债 P2 下轮补）
---

## 背景
方案 C「帮我设计」chat agent 一天内 kickoff→prod 闭环，质量由 **e2e mock 全链 + qa 真文本真图实拍 + QA 0048 验收 8/8** 保住（真实行为已验），但**后端单测护栏未随代码同批补齐**（既有 68 单测保绿=零回归，新增 chat 链路自身单测是债）。coordinator #918 明确列为 P2 backlog、dev 下轮补。

## 待补单测面（dev 细化，建议覆盖）
- **ChatOrchestrator tool-use 循环**：澄清轮→结构化 tool args（=/listing 请求体字段，不直出 prompt）→费用闸→确认经 launcher 出图→转发 job_event→收尾。
- **文本 LLM adapter**：`reasoning_content` 过滤（thinking 模型内部推理绝不混进 assistant_delta）；thinking 开关透传；ep- model id 原样传。
- **confirm_token**：一次性（重放拒）+ 绑 session/user + TTL 10min。
- **会话级出图闸**：`chat_session_max_jobs=5` 可配、超限拒。
- **fail-fast**：LLM 不可用报错不装死；非法参数（如占位问句进 ratio）**进费用闸前拦下转澄清**（#904 修的坑，务必有回归单测锁）；跨用户会话隔离（owner 404）。

## 处理记录
- 2026-07-02 [PM] coordinator #918 收口备忘入档：chat agent 后端 pytest 测试债 P2、dev 下轮补。
  非阻断（e2e+验收已过、既有 68 单测零回归），但缺单测护栏是回归风险面，排 P2 待 dev 补。
  **尤其「占位参数进费用闸前拦下转澄清」（#904/#906 修）建议锁回归单测**——这是真 LLM 健壮性坑。owner=开发。
