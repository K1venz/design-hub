---
id: ISSUE-0049
title: 「帮我设计」chat agent 后端 pytest 测试债（方案 C 上线时以 e2e/冒烟验、单测未补齐）
status: 待验证        # dev #921 现补（非下轮）：+22 单测、全量 90 绿（060f181），owner 交 QA
severity: P2          # chat 已上线 prod、e2e+验收 8/8 已过，但缺单测护栏=回归风险面
reporter: PM          # coordinator #918 收口备忘，PM 入档
owner: QA             # dev 已补（060f181），QA 验单测覆盖面 + 跑绿
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
- 2026-07-02 [dev] **现补完成（coordinator #921「不用等下轮、真实用户 bug 可中断」）**：手工 E2E harness
  固化为 committed pytest，**+22 测试、全量 90 绿**（commit 060f181，ruff/mypy(src)/pytest 全绿）。
  覆盖 PM 列的全部面：
  · `tests/test_chat.py`(16)：ChatOrchestrator 事件序 / 费用闸（cost_confirm 暂停不出图）/ confirm 启
    job + job_event 转发 / confirm_token **一次性·跨用户·cancel·过期** / 会话级出图闸（max_session_jobs）/
    **占位 ratio→转澄清（#904 坑，回归单测已锁 ✓）** / 澄清轮无工具；`ListingJobLauncher.validate` 纯校验
    （坏比例/非自有图/clone 双角色/edit delta-ratio 冲突）；`InMemorySessionStore` token 语义。
  · `tests/test_text_llm_adapter.py`(6)：`OpenAICompatTextProvider`——**reasoning_content 过滤**（含出图轮
    content 空、推理走 reasoning_content 的真场景，推理零泄漏）/ tool_calls 跨 chunk 分片拼接 / extra_body
    （thinking 关）透传 / 非 2xx→TextLLMError / 坏 JSON→报错。httpx MockTransport 无网络、零成本。
  真出图链走 mock 图像 provider + 真 InMemoryEventBus/InProcessTaskQueue + sqlite，确定性 StubTextLLM。
  status→待验证、owner→QA（验覆盖面 + 跑绿）。
