"""Chat harness（ISSUE-0059 A 线）：知识库加载 + 四段 system prompt + 长会话上下文裁剪。"""

from design_hub.application.chat.orchestrator import (
    _CONTEXT_MAX_MESSAGES,
    _to_llm_messages,
    _tool_specs,
)
from design_hub.application.chat.ratio_intent import decide_chat_ratio
from design_hub.application.chat.system_prompt import (
    build_system_prompt,
    default_system_prompt,
    load_chat_knowledge,
)
from design_hub.domain.models import ChatMessageRecord, ChatTranscript


def _transcript(n: int) -> ChatTranscript:
    msgs = tuple(
        ChatMessageRecord(
            seq=i, role=("user" if i % 2 == 0 else "assistant"), content=f"m{i}"
        )
        for i in range(n)
    )
    return ChatTranscript(id="s", title="t", messages=msgs)


def test_load_chat_knowledge_strips_comment_and_has_features() -> None:
    kb = load_chat_knowledge()
    assert "<!--" not in kb  # 维护者注释头不注入 LLM 上下文
    assert "商品套图" in kb and "暂不支持" in kb  # 功能地图 + 防编造段
    assert "换背景" in kb and "反推提示词" in kb


def test_chat_knowledge_removes_stale_capability_claims() -> None:
    knowledge = load_chat_knowledge()

    for stale in (
        "按张扣积分",
        "右上角「内测免费」",
        "登录一般不会中途掉线",
        "历史图和首页案例图都能看「配方」",
        "AI 一键消除/智能扩图（预告中未上线）",
        "按张计入出图额度",
        "用户在创作页面选择要使用的模型",
        "引导其回创作页面完成选择",
    ):
        assert stale not in knowledge
    for current in (
        "统一模型选择器",
        "文本模型",
        "图片模型",
        "反推提示词",
        "以页面当前显示的可用模型为准",
        "钱包与价格信息目前暂未公开",
        "仅商品套图任务支持一键复用",
        "当前工作台选择器暂未提供 4:3",
        "暂无专用按钮、画笔、蒙版",
        "通用自然语言生图",
    ):
        assert current in knowledge


def test_build_system_prompt_has_four_segments_and_embeds_knowledge() -> None:
    p = build_system_prompt("KNOWLEDGE_MARKER_XYZ")
    assert "你的身份" in p  # persona
    assert "平台知识库" in p and "KNOWLEDGE_MARKER_XYZ" in p  # 知识库段注入
    assert "出图工具契约" in p  # 工具契约
    assert "守则" in p and "不编造" in p and "用户选择的模型" in p
    assert "用户确认" in p and "不收费" not in p
    assert "不得讨论或编造价格、额度、钱包、充值与套餐" not in p
    assert "三环" in p  # 三环边界
    assert "Chat 统一模型选择器" in p
    assert "不得自行更换、猜测或代为选择" in p
    assert "用户在创作页面选择" not in p


def test_default_system_prompt_embeds_real_knowledge() -> None:
    p = default_system_prompt()
    assert "商品套图" in p and "暂不支持" in p


def test_build_system_prompt_uses_determined_ratio_without_asking() -> None:
    prompt = build_system_prompt("KB")
    assert "1:1 / 3:4 / 4:3 / 9:16 / 16:9" in prompt
    assert "本轮确定比例" in prompt
    assert "不要追问比例" in prompt
    assert "未明确套图或张数时，按单图 n=1" in prompt


def test_generate_tool_uses_determined_ratio() -> None:
    generate = next(tool for tool in _tool_specs() if tool.name == "generate")
    assert "确定比例由系统备注提供" in generate.description


def test_chat_exposes_minimal_background_reverse_and_page_tools() -> None:
    tools = {tool.name: tool for tool in _tool_specs()}

    assert {
        "replace_background",
        "reverse_prompt",
        "open_feature",
    } <= tools.keys()
    assert "quality" not in tools["replace_background"].parameters["properties"]
    assert tools["open_feature"].parameters["properties"]["feature"]["const"] == (
        "background_replace"
    )


def test_chat_describes_background_replacement_fidelity_boundary() -> None:
    knowledge = load_chat_knowledge()
    tool = next(item for item in _tool_specs() if item.name == "replace_background")

    for required in (
        "主体清晰、背景可分离",
        "包装文字尽量保留",
        "大面积文案",
        "复杂排版",
    ):
        assert required in knowledge
    assert "不能保证像素级保真" in tool.description


def test_chat_write_tool_schemas_never_expose_listing_only_fields() -> None:
    for name in ("generate", "clone", "edit"):
        tool = next(item for item in _tool_specs() if item.name == name)
        assert "category" not in tool.parameters["properties"]
        assert "modifiers" not in tool.parameters["properties"]


def test_system_prompt_requires_category_free_conservative_enhancement() -> None:
    prompt = default_system_prompt()
    for forbidden in (
        'category 默认 "FOOD"',
        "食品 / 服装 / 美妆 / 鞋类 / 数码",
        "自动识别品类",
    ):
        assert forbidden not in prompt
    for required in (
        "不得询问、推断或填写品类",
        "不得生成 modifiers 字段",
        "风格只写入 prompt",
        "同一次工具调用",
        "不得编造品牌",
        "不得编造卖点",
        "至少上传一张图片",
    ):
        assert required in prompt


def test_system_prompt_separates_design_discussion_from_generation_intent() -> None:
    prompt = default_system_prompt()
    for required in (
        "只有用户明确要求生成、制作、复刻或编辑成品",
        "分析、建议、讨论、比较或头脑风暴",
        "不得调用 generate、clone、edit",
        "不要把上传图片本身视为生图授权",
        "意图模糊",
    ):
        assert required in prompt


def test_system_prompt_prefers_direct_execution_over_page_routing() -> None:
    prompt = default_system_prompt()

    for required in (
        "replace_background",
        "reverse_prompt",
        "信息完整时直接调用",
        "只追问缺失项",
        "open_feature",
        "不得用页面跳转代替直接执行",
    ):
        assert required in prompt


def test_system_prompt_explains_current_turn_only_4k_rules_without_internal_model_name() -> None:
    prompt = default_system_prompt()
    for required in (
        "本轮明确写出",
        "4K",
        "16:9",
        "高清",
        "完整生图/改图需求",
        "直接进入生成流程",
    ):
        assert required in prompt
    assert "gpt-image-2-4k" not in prompt


def test_current_ratio_and_edit_source_are_added_only_to_latest_user_message() -> None:
    transcript = _transcript(3)
    out = _to_llm_messages(
        transcript,
        current_ratio=decide_chat_ratio("做横版", "3:4"),
        edit_source_image_key="selected.png",
    )
    assert "本轮确定比例=4:3" in out[-1].content
    assert "source_image_key=selected.png" in out[-1].content
    assert all("本轮确定比例=" not in message.content for message in out[:-1])
    assert all("source_image_key=" not in message.content for message in out[:-1])


def test_context_no_truncation_when_within_budget() -> None:
    out = _to_llm_messages(_transcript(_CONTEXT_MAX_MESSAGES))
    assert len(out) == _CONTEXT_MAX_MESSAGES
    assert all("省略" not in m.content for m in out)  # 未裁剪、无省略备注


def test_context_truncates_long_keeps_head_and_recent() -> None:
    n = _CONTEXT_MAX_MESSAGES + 20
    out = _to_llm_messages(_transcript(n))
    assert len(out) == _CONTEXT_MAX_MESSAGES + 1  # 首条 + 省略备注 + 最近
    assert out[0].content == "m0"  # 首条(原始诉求)保留
    assert any("省略" in m.content for m in out)  # 省略备注在
    assert out[-1].content == f"m{n - 1}"  # 最近一条保留
