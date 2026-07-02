"""ChatOrchestrator（方案 C 零框架 tool-use 循环）。

多轮澄清 → LLM 产结构化 tool_call（= /listing 请求体字段，绝不直出图像 prompt，铁律①）
→ 费用确认闸（暂停）→ 用户确认 → 经 ListingJobLauncher 走同一出图链（频控/owner/
成本守卫/卡链全继承，#884⑤）→ 转发 job SSE（包一层 job_event）→ 收尾话术。

产出 ChatEvent 流，由 /chat 路由序列化为 SSE。MVP 会话内存态、不落库。
"""

from collections.abc import AsyncIterator
from dataclasses import dataclass, field
from typing import Any

from design_hub.application.chat.session_store import (
    InMemorySessionStore,
    PendingAction,
)
from design_hub.application.listing.job_launcher import ListingJobLauncher
from design_hub.application.listing.requests import (
    CloneRequest,
    EditRequest,
    ListingGenerateRequest,
)
from design_hub.application.rate_limit import RateLimited
from design_hub.application.registry import ProviderRegistry
from design_hub.domain.enums import ModelName, TaskEventType
from design_hub.domain.errors import BudgetExceeded, NotFoundError
from design_hub.domain.models import AuthUser
from design_hub.ports.events import EventStream
from design_hub.ports.text_llm import (
    ChatMessage,
    TextChunk,
    TextLLMError,
    TextLLMPort,
    ToolCall,
    ToolSpec,
)

_SYSTEM_PROMPT = """你是「实朴电商图片工作站」的设计助手，通过对话帮用户出电商商品图。
你有三个工具（都是异步出图；出图前系统会显示预计费用并等用户确认）：
- generate：出图。单图流填 n（1..7 张）；套图填 plan（图型→张数，
  图型只能是 白底/场景/卖点，Σ 3..10）；n 与 plan 互斥、恰填其一。
  需要 upload_ids（用户上传的产品图，1..3 张）。
- clone：爆款复刻。product_upload_ids 恰 1 张 + reference_upload_ids 爆款参考 1..2 张；
  clone_mode 为『参考风格』或『高度复刻』。
- edit：二次编辑已产出的图。需 source_image_key + prompt + edit_mode（delta 微调 / full 重做）。
参数约束（必须遵守）：
- ratio 只能取 1:1 / 3:4 / 9:16 / 16:9 之一；用户没指定就默认填 "1:1"。
- category 默认 "FOOD"（食品），除非用户明确是别的品类。
- generate 的 n 取 1..7；套图 plan 图型只能是 白底/场景/卖点、Σ 3..10。
规则：
1. 信息不全（缺是否有产品图等）先用自然语言追问澄清，别乱猜。
2. **绝不要把问题、占位符或「请问…」之类的文字填进任何工具参数**。必填字段
   （尤其 upload_ids、ratio）不确定时，用自然语言追问，**不要调用工具**。
3. 只输出工具参数这类结构化字段；prompt 字段填用户的自然语言意图即可，
   不要自己编写发给图像模型的最终提示词。
4. 每轮系统会在用户消息里以 [系统备注] upload_ids=... 告诉你本轮可用的产品图 id，
   调用工具时把这些 id **原样**填进 upload_ids/product_upload_ids。
"""


@dataclass(frozen=True)
class ChatEvent:
    """对话流事件（路由序列化为 SSE：event: <type>\\ndata: <json>）。"""

    type: str
    data: dict[str, Any]


def _tool_specs() -> list[ToolSpec]:
    # 工具参数 schema 直接取自请求 DTO（单一事实源，与 launcher 校验同源）
    return [
        ToolSpec(
            "generate", "出图：单图流(n)或套图(plan)", ListingGenerateRequest.model_json_schema()
        ),
        ToolSpec("clone", "爆款图复刻", CloneRequest.model_json_schema()),
        ToolSpec("edit", "二次编辑已产出的图", EditRequest.model_json_schema()),
    ]


@dataclass
class ChatOrchestrator:
    text_llm: TextLLMPort
    launcher: ListingJobLauncher
    event_stream: EventStream
    registry: ProviderRegistry
    sessions: InMemorySessionStore
    max_session_jobs: int = 5  # 会话级出图闸（#884②）
    image_model: ModelName = ModelName.GPT_IMAGE_2
    _tools: list[ToolSpec] = field(default_factory=_tool_specs)

    async def handle_message(
        self, user: AuthUser, session_id: str | None, message: str, upload_ids: list[str]
    ) -> AsyncIterator[ChatEvent]:
        if session_id is None:
            session = self.sessions.create(user.user_id)
        else:
            got = self.sessions.get(session_id, user.user_id)
            if got is None:
                yield ChatEvent("error", {"code": "bad_request", "message": "会话不存在或无权访问"})
                yield ChatEvent("assistant_end", {"status": "error"})
                return
            session = got
        yield ChatEvent("session", {"session_id": session.session_id})
        session.pending = None  # 新消息作废旧 pending（重新规划）

        content = message
        if upload_ids:
            content = f"{message}\n\n[系统备注] 本轮可用产品图 upload_ids={','.join(upload_ids)}"
        session.messages.append(ChatMessage(role="user", content=content))

        llm_messages = [ChatMessage(role="system", content=_SYSTEM_PROMPT), *session.messages]
        assistant_text = ""
        tool_calls: tuple[ToolCall, ...] = ()
        try:
            async for chunk in self.text_llm.complete(messages=llm_messages, tools=self._tools):
                if isinstance(chunk, TextChunk):
                    assistant_text += chunk.text
                    yield ChatEvent("assistant_delta", {"text": chunk.text})
                else:
                    tool_calls = chunk.tool_calls
        except TextLLMError as exc:
            yield ChatEvent("error", {"code": "llm_unavailable", "message": str(exc)})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        session.messages.append(
            ChatMessage(role="assistant", content=assistant_text, tool_calls=tool_calls)
        )
        if not tool_calls:
            yield ChatEvent("assistant_end", {"status": "complete"})
            return

        call = tool_calls[0]  # MVP：一轮一工具
        yield ChatEvent("step", {"phase": "planning", "detail": "正在规划出图参数"})
        try:
            req = self._parse_req(call.name, call.arguments)
        except Exception as exc:  # pydantic 校验失败（含 extra=forbid）→ 明确报错
            yield ChatEvent("error", {"code": "bad_request", "message": f"工具参数不合法：{exc}"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        try:
            # 与出图同一校验源（#884⑤）：LLM 产的非法参数（占位/缺比例/非自有图等）
            # 在进费用闸前拦下，转澄清——不让用户确认一个注定失败的出图（防「确认后才报错」）。
            self.launcher.validate(user, req)
        except (ValueError, NotFoundError) as exc:
            yield ChatEvent(
                "assistant_delta",
                {"text": f"还差点信息、暂时没法出图（{exc}）。麻烦补充一下，我再帮你安排。"},
            )
            yield ChatEvent("assistant_end", {"status": "complete"})
            return
        yield ChatEvent("tool_call", {"tool": call.name, "args": call.arguments})

        count = self._count(call.name, req)
        unit_cost = self.registry.get(self.image_model).unit_cost  # 与工作台同源（#884③）
        estimate = unit_cost * count
        # 只保留被选中的 tool_call（收尾轮 tool 消息按其 id 回链）
        session.messages[-1] = ChatMessage(
            role="assistant", content=assistant_text, tool_calls=(call,)
        )
        pending = self.sessions.new_pending(
            session, tool=call.name, req=req, count=count, estimate=estimate, tool_call_id=call.id
        )
        yield ChatEvent(
            "cost_confirm",
            {
                "confirm_token": pending.confirm_token,
                "tool": call.name,
                "args": call.arguments,
                "count": count,
                "unit_cost": str(unit_cost),
                "estimate_cny": str(estimate),
            },
        )
        yield ChatEvent("assistant_end", {"status": "awaiting_confirm"})

    async def handle_confirm(
        self, user: AuthUser, session_id: str, confirm_token: str, action: str
    ) -> AsyncIterator[ChatEvent]:
        session = self.sessions.get(session_id, user.user_id)
        if session is None:
            yield ChatEvent("error", {"code": "bad_request", "message": "会话不存在或无权访问"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        yield ChatEvent("session", {"session_id": session.session_id})

        if action == "cancel":
            self.sessions.cancel_pending(session)
            yield ChatEvent("assistant_delta", {"text": "已取消本次出图。"})
            yield ChatEvent("assistant_end", {"status": "complete"})
            return
        if action != "confirm":
            yield ChatEvent("error", {"code": "bad_request", "message": f"未知 action：{action}"})
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        pending = self.sessions.take_pending(session, confirm_token)
        if pending is None:
            yield ChatEvent(
                "error",
                {"code": "invalid_confirm_token", "message": "确认令牌无效或已过期，请重新发起。"},
            )
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        if session.job_count >= self.max_session_jobs:  # 会话级闸（#884②）：启 job 前查
            yield ChatEvent(
                "error",
                {
                    "code": "session_job_limit",
                    "message": f"本次会话出图已达上限（{self.max_session_jobs} 单），请开新会话。",
                },
            )
            yield ChatEvent("assistant_end", {"status": "error"})
            return

        try:
            job_id = await self._launch(user, pending)
        except (ValueError, NotFoundError, RateLimited, BudgetExceeded) as exc:
            yield ChatEvent("error", {"code": self._err_code(exc), "message": str(exc)})
            yield ChatEvent("assistant_end", {"status": "error"})
            return
        session.job_count += 1
        # plan（套图图型→张数）随 job_started 下发，前端可预铺分组槽（coordinator 可选优化）
        plan = pending.req.plan if isinstance(pending.req, ListingGenerateRequest) else None
        yield ChatEvent(
            "job_started",
            {"job_id": job_id, "tool": pending.tool, "count": pending.count, "plan": plan},
        )

        completed = False
        async for event in self.event_stream.subscribe(job_id):
            yield ChatEvent(
                "job_event", {"job_id": job_id, "type": event.type.value, "data": event.data}
            )
            if event.type == TaskEventType.TASK_COMPLETED:
                completed = True

        # 收尾轮：喂 tool 结果 → LLM 产自然收尾语（无工具）
        summary = "出图完成" if completed else "出图失败或部分失败"
        session.messages.append(
            ChatMessage(
                role="tool",
                content=f"{pending.tool} 结果：{summary}",
                tool_call_id=pending.tool_call_id,
            )
        )
        closing = ""
        try:
            llm_messages = [ChatMessage(role="system", content=_SYSTEM_PROMPT), *session.messages]
            async for chunk in self.text_llm.complete(messages=llm_messages, tools=[]):
                if isinstance(chunk, TextChunk):
                    closing += chunk.text
                    yield ChatEvent("assistant_delta", {"text": chunk.text})
        except TextLLMError:
            fallback = "已完成，可在结果区查看。" if completed else "很抱歉，出图未成功，请重试。"
            yield ChatEvent("assistant_delta", {"text": fallback})
            closing = fallback
        session.messages.append(ChatMessage(role="assistant", content=closing))
        yield ChatEvent("assistant_end", {"status": "complete"})

    async def _launch(self, user: AuthUser, pending: PendingAction) -> str:
        req = pending.req
        if pending.tool == "generate" and isinstance(req, ListingGenerateRequest):
            return await self.launcher.launch_generate(user, req)
        if pending.tool == "clone" and isinstance(req, CloneRequest):
            return await self.launcher.launch_clone(user, req)
        if pending.tool == "edit" and isinstance(req, EditRequest):
            return await self.launcher.launch_edit(user, req)
        raise ValueError(f"未知工具：{pending.tool}")

    @staticmethod
    def _parse_req(
        tool: str, args: dict[str, Any]
    ) -> ListingGenerateRequest | CloneRequest | EditRequest:
        if tool == "generate":
            return ListingGenerateRequest(**args)
        if tool == "clone":
            return CloneRequest(**args)
        if tool == "edit":
            return EditRequest(**args)
        raise ValueError(f"未知工具：{tool}")

    @staticmethod
    def _count(
        tool: str, req: ListingGenerateRequest | CloneRequest | EditRequest
    ) -> int:
        if tool == "generate" and isinstance(req, ListingGenerateRequest):
            if req.n is not None:
                return req.n
            if req.plan is not None:
                return sum(req.plan.values())
        return 1

    @staticmethod
    def _err_code(exc: Exception) -> str:
        if isinstance(exc, RateLimited):
            return "rate_limited"
        if isinstance(exc, BudgetExceeded):
            return "budget_exceeded"
        return "bad_request"  # ValueError / NotFoundError
