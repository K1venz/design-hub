import pytest

from design_hub.application.image_generation.prompt_policy import compose_image_api_prompt


def test_compose_image_api_prompt_orders_policy_task_and_negative() -> None:
    prompt = compose_image_api_prompt("生成红色水杯", "不要水印")

    assert prompt.startswith("【全局真实性与细节质量约束】")
    assert prompt.index("【本次生图要求】") < prompt.index("生成红色水杯")
    assert prompt.index("生成红色水杯") < prompt.index("【需要避免】")
    assert prompt.endswith("不要水印")
    assert prompt.count("【全局真实性与细节质量约束】") == 1


def test_compose_image_api_prompt_omits_empty_negative_section() -> None:
    prompt = compose_image_api_prompt("生成扁平 Logo", "")

    assert "【需要避免】" not in prompt


def test_compose_image_api_prompt_rejects_empty_task_prompt() -> None:
    with pytest.raises(ValueError, match="task prompt"):
        compose_image_api_prompt("   ", "")
